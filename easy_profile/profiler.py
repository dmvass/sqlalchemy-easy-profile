from collections import Counter, namedtuple
import functools
import sys
import time
import inspect
from queue import Queue
import re

from sqlalchemy import event
from sqlalchemy.engine.base import Engine

from .reporters import StreamReporter

# Optimize timer function for the platform
if sys.platform == 'win32':
    _timer = time.clock
else:
    _timer = time.time


SQL_OPERATORS = ["select", "insert", "update", "delete"]
OPERATOR_REGEX = re.compile("(%s) *." % "|".join(SQL_OPERATORS), re.IGNORECASE)


def _get_object_name(obj):
    module = getattr("__module__", obj, inspect.getmodule(obj).__name__)
    if hasattr(obj, "__qualname__"):
        name = obj.__qualname__
    else:
        name = obj.__name__
    return module + "." + name


_DebugQuery = namedtuple(
    "_DebugQuery", "statement,parameters,start_time,end_time"
)


class DebugQuery(_DebugQuery):
    """Public implementation of the debug query class"""

    @property
    def duration(self):
        return self.end_time - self.start_time


class SessionProfiler:
    """A session profiler for sqlalchemy queries.

    The profiling session hooks into SQLAlchmey and captures query text,
    duration information, and query parameters. You also may have multiple
    profiling sessions active at the same time on the same or different
    Engines. If multiple profiling sessions are active on the same engine,
    queries on that engine will be collected by both sessions and reported
    on different reporters.

    You may begin and commit a profiling session as much as you like.
    Calling begin on an already started session or commit on an already
    committed session will raise an :class:`AssertionError`. You also can
    use a contextmanager interface for session profiling or used it like a
    decorator. This has the effect of only profiling queries occurred within
    the decorated function or inside a manager context.

    :param engine: sqlalchemy database engine
    :type engine: Engine
    """

    _before = "before_cursor_execute"
    _after = "after_cursor_execute"

    def __init__(self, engine=None):
        if engine is None:
            self.engine = Engine
            self.db_name = "default"
        else:
            self.engine = engine
            self.db_name = engine.url.database

        self.alive = False
        self.queries = None

        self._stats = None

    def __enter__(self):
        self.begin()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.commit()

    def __call__(self, path=None, path_callback=None, reporter=None):
        """Decorate callable object and profile sqlalchemy queries.

        If reporter was not defined by default will be used a base
        streaming reporter.

        :param reporter: profiling reporter
        :type reporter: easy_profile.reporters.Reporter

        :param path_callback: callback for getting more complex path
        :type path_callback: collections.abc.Callable
        """
        if reporter is None:
            reporter = StreamReporter()

        def decorator(func):

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if path_callback is not None:
                    _path = path_callback(func, *args, **kwargs)
                else:
                    _path = path or _get_object_name(func)

                self.begin()
                try:
                    result = func(*args, **kwargs)
                finally:
                    self.commit()
                    reporter.report(_path, self.stats)
                return result

            return wrapper

        return decorator

    @property
    def stats(self):
        if self._stats is None:
            self._reset_stats()
        return self._stats

    def begin(self):
        """Begin profiling session.

        :raises AssertionError: When the session is already alive.
        """
        if self.alive:
            raise AssertionError("Profiling session is already began")

        self.alive = True
        self.queries = Queue()
        self._reset_stats()

        event.listen(self.engine, self._before, self._before_cursor_execute)
        event.listen(self.engine, self._after, self._after_cursor_execute)

    def commit(self):
        """Commit profiling session.

        :raises AssertionError: When the session is not alive.
        """
        if not self.alive:
            raise AssertionError("Profiling session is already committed")

        self.alive = False
        self._get_stats()

        event.remove(self.engine, self._before, self._before_cursor_execute)
        event.remove(self.engine, self._after, self._after_cursor_execute)

    def _get_stats(self):
        """Calculate and returns session statistics."""
        while not self.queries.empty():
            query = self.queries.get()
            self._stats["call_stack"].append(query)
            match = OPERATOR_REGEX.match(query.statement)
            if match:
                self._stats[match.group(1).lower()] += 1
                self._stats["total"] += 1
                self._stats["duration"] += query.duration
                self._stats["duplicates"][query.statement] += 1

        return self._stats

    def _reset_stats(self):
        counters = ["total", "duration", *SQL_OPERATORS]
        self._stats = dict(zip(counters, [0] * len(counters)))
        self._stats["call_stack"] = []
        self._stats["duplicates"] = Counter()
        self._stats["db"] = self.db_name

    def _before_cursor_execute(self, conn, cursor, statement, parameters,
                               context, executemany):
        context._query_start_time = _timer()

    def _after_cursor_execute(self, conn, cursor, statement, parameters,
                              context, executemany):
        self.queries.put(DebugQuery(
            statement, parameters, context._query_start_time, _timer()
        ))
