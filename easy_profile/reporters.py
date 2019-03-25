from abc import ABCMeta, abstractmethod
from collections import OrderedDict
from functools import partial
import operator
import sys
import textwrap

import six

from .termcolors import colorize

_decrement = partial(operator.add, -1)


def shorten(text, length, placeholder="..."):
    """Truncate the given text to fit in the given length.

    :param text: string for truncate
    :type text: str

    :param length: max length of string
    :type length: int

    :param placeholder: append to the end of truncated text
    :type placeholder: str

    :return: truncated string

    """
    if len(text) > length:
        return text[:length - len(placeholder)] + placeholder
    return text


@six.add_metaclass(ABCMeta)
class Reporter(object):
    """Abstract class for profiler reporters"""

    @abstractmethod
    def report(self, path, stats):
        """Reports profiling statistic to a stream.

        :param path: where profiling occurred
        :type path: str

        :param stats: profiling statistics
        :type stats: dict

        """


class StreamReporter(Reporter):
    """A base reporter for streaming to a file. By default reports
    will be written to ``sys.stdout``.

    :param medium: a medium threshold count
    :type medium: int

    :param high: a medium threshold count
    :type high: int

    :param file: output

    :param colorized:
    :type colorized: bool

    :param display_duplicates:
    :type display_duplicates: display_duplicates

    """

    _display_names = OrderedDict([
        ("Database", "db"),
        ("SELECT", "select"),
        ("INSERT", "insert"),
        ("UPDATE", "update"),
        ("DELETE", "delete"),
        ("Totals", "total"),
        ("Duplicates", "duplicates_count"),
    ])

    def __init__(self,
                 medium=50,
                 high=100,
                 file=sys.stdout,
                 colorized=True,
                 display_duplicates=5):

        if medium >= high:
            raise ValueError("Medium must be less than high")
        self._medium = medium
        self._high = high
        self._file = file
        self._colorized = colorized
        self._display_duplicates = display_duplicates or 0

    def report(self, path, stats):
        duplicates = stats["duplicates"]
        stats["duplicates_count"] = sum(map(_decrement, duplicates.values()))
        stats["db"] = shorten(stats["db"], 10)

        output = self._colorize("\n{0}\n".format(path), ["bold"], fg="blue")
        output += self.stats_table(stats)

        total = stats["total"]
        duration = float(stats["duration"])
        summary = "Total queries: {0} in {1:.3}s".format(total, duration)
        output += self._info_line("\n{0}\n".format(summary), total)

        # Display duplicated sql statements.
        #
        # Get top counters were value greater than 1 and write to
        # a stream. It will be skipped if `display_duplicates` was
        # set to `0` or `None`.
        most_common = duplicates.most_common(self._display_duplicates)
        for statement, count in most_common:
            if count > 1:
                # Wrap SQL statement and returning a list of wrapped lines
                statement = textwrap.fill(statement)
                text = "\nRepeated {0} times:\n{1}\n".format(count, statement)
                output += self._info_line(text, count)

        self._file.write(output)

    def stats_table(self, stats, sep="|"):
        """Formats profiling statistics as table.

        :param stats: profiling statistics
        :type stats: dict

        :param sep: columns separator character
        :type sep: str

        :return: formatted table
        :rtype: str

        """
        line = sep + "{}" + sep + "\n"
        h_names = [n.center(len(n) + 2) for n in self._display_names]
        breakline = line.format(sep.join("-" * len(n) for n in h_names))

        # Creates table and writes a header
        output = ""
        output += breakline
        output += line.format(sep.join(h_names))
        output += breakline

        # Formats and writes row values in order by display_names.
        #
        # Row with values can be colorized for better perception. It's
        # can be activated/deactivated through `colorized` parameter.
        values = []
        for name, key in self._display_names.items():
            value = stats[key]
            size = len(name) + 2
            values.append(str(value).center(size))

        row = line.format(sep.join(values))
        output += self._info_line(row, stats["total"])
        output += breakline

        return output

    def _info_line(self, line, total):
        """Returns colorized text according threshold.

        :param line: text which will be colorized
        :type line: str

        :param total: threshold count
        :type total: int

        :return: colorized text

        """
        if total > self._high:
            return self._colorize(line, ["bold"], fg="red")
        elif total > self._medium:
            return self._colorize(line, ["bold"], fg="yellow")
        return self._colorize(line, ["bold"], fg="green")

    def _colorize(self, text, opts=(), fg=None, bg=None):
        if not self._colorized:
            return text
        return colorize(text, opts, fg=fg, bg=bg)
