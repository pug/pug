'''NLP utilities for use with django models and querysets and ORM (SQL)

Intended only for use within a Django project (requires django.db, which itself requires settings)

TODO: Move all functions that depend on a properly configured django.conf.settings to pug.db or pug.dj
'''

import types
import re
import string
import os
import csv
import datetime
import dateutil
import pytz
import warnings
from collections import Counter

#import math
from pytz import timezone
from collections import OrderedDict
from collections import Mapping
from progressbar import ProgressBar

import character_subset as chars
import regex_patterns as rep

import numpy as np
import scipy as sci

import logging
logger = logging.getLogger('bigdata.info')

import ascii

#from django.core.exceptions import ImproperlyConfigured
# try:
#     import django.db
# except ImproperlyConfigured:
#     import traceback
#     print traceback.format_exc()
#     print 'WARNING: The module named %r from file %r' % (__name__, __file__)
#     print '         can only be used within a Django project!'
#     print '         Though the module was imported, some of its functions may raise exceptions.'



NUMERIC_TYPES = (float, long, int)
SCALAR_TYPES = (float, long, int, str, unicode)  # bool, complex, datetime.datetime
# numpy types are derived from these so no need to include numpy.float64, numpy.int64 etc
DICTABLE_TYPES = (Mapping, tuple, list)  # convertable to a dictionary (inherits collections.Mapping or is a list of key/value pairs)
VECTOR_TYPES = (list, tuple)
PYTHON_NUMBER_TYPES = (float, long, int)  # bool, complex, datetime.datetime,
PUNC = unicode(string.punctuation)

RE_WORD_SPLIT_IGNORE_EXTERNAL_APOSTROPHIES = re.compile('\W*\s\'{1,3}|\'{1,3}\W+|[^-\'_.a-zA-Z0-9]+|\W+\s+')
RE_WORD_SPLIT_PERMISSIVE = re.compile('[^-\'_.a-zA-Z0-9]+|[^\'a-zA-Z0-9]\s\W*')
RE_SENTENCE_SPLIT = re.compile('[.?!](\W+)|$')
RE_MONTH_NAME = re.compile('(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[acbeihmlosruty]*', re.IGNORECASE)

# MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
# MONTH_PREFIXES = [m[:3] for m in MONTHS]
# MONTH_SUFFIXES = [m[3:] for m in MONTHS]
# SUFFIX_LETTERS = ''.join(set(''.join(MONTH_SUFFIXES)))


try:
    from django.conf import settings
    DEFAULT_TZ = timezone(settings.TIME_ZONE)
except:
    DEFAULT_TZ = timezone('UTC')


def qs_to_table(qs, excluded_fields=['id']):
    rows, rowl = [], []
    qs = qs.all()
    fields = sorted(qs[0]._meta.get_all_field_names())
    for row in qs:
        for f in fields:
            if f in excluded_fields:
                continue
            rowl += [getattr(row,f)]
        rows, rowl = rows + [rowl], []
    return rows


def reverse_dict(d):
    return dict((v, k) for (k, v) in dict(d).iteritems())


def reverse_dict_of_lists(d):
    ans = {}
    for (k, v) in dict(d).iteritems():
        for new_k in list(v):
            ans[new_k] = k
    return ans


def clean_field_dict(field_dict, cleaner=unicode.strip, time_zone=None):
    r"""Normalize text field values by stripping leading and trailing whitespace

    >>> sorted(clean_field_dict({'_state': object(), 'x': 1, 'y': u"\t  Wash Me! \n" }).items())
    [('x', 1), ('y', u'Wash Me!')]
    """
    d = {}
    if time_zone is None:
        tz = DEFAULT_TZ
    for k, v in field_dict.iteritems():
        if k == '_state':
            continue
        if isinstance(v, basestring):
            d[k] = cleaner(unicode(v))
        elif isinstance(v, (datetime.datetime, datetime.date)):
            d[k] = tz.localize(v)
        else:
            d[k] = v
    return d


def quantify_field_dict(field_dict, precision=None, date_precision=None, cleaner=unicode.strip):
    r"""Convert text and datetime dict values into float/int/long, if possible

    FIXME: this test probably needs to define a time zone for the datetime object
    >>> sorted(quantify_field_dict({'_state': object(), 'x': 12345678911131517L, 'y': "\t  Wash Me! \n", 'z': datetime.datetime(1970, 10, 23, 23, 59, 59, 123456)}).items())
    [('x', 12345678911131517L), ('y', u'Wash Me!'), ('z', 25592399.123456)]
    """
    d = clean_field_dict(field_dict)
    for k, v in d.iteritems():
        if isinstance(d[k], datetime.datetime):
            # seconds since epoch = datetime.datetime(1969,12,31,18,0,0)
            try:
                # around the year 2250, a float conversion of this string will lose 1 microsecond of precision, and around 22500 the loss of precision will be 10 microseconds
                d[k] = float(d[k].strftime('%s.%f'))
                if date_precision is not None and isinstance(d[k], NUMERIC_TYPES):
                    d[k] = round(d[k], precision)
                    # rounding to `precision` skipped if `date_precision` already has been applied!
                    continue
            except:
                pass
        if not isinstance(d[k], NUMERIC_TYPES):
            try:
                d[k] = float(d[k])
            except:
                pass
        if precision is not None and isinstance(d[k], NUMERIC_TYPES):
            d[k] = round(d[k], precision)
        if isinstance(d[k], float) and d[k].is_integer():
            # `int()` will convert to a long, if value overflows an integer type
            # use the original value, `v`, in case it was a long and d[k] is has been truncated by the conversion to float!
            d[k] = int(v)
    return d


def generate_batches(sequence, batch_len=1, allow_partial=True):
    """Iterate through a sequence (or generator) in batches of length `batch_len`

    http://stackoverflow.com/a/761125/623735
    >>> [batch for batch in generate_batches(range(7), 3)]
    [[0, 1, 2], [3, 4, 5], [6]]
    """
    it = iter(sequence)
    last_value = False
    # An exception will be thrown by `.next()` here and caught in the loop that called this iterator/generator 
    while not last_value:
        batch = []
        for n in xrange(batch_len):
            try:
                batch += (it.next(),)
            except StopIteration:
                last_value = True
                if batch:
                    break
                else:
                    raise StopIteration       
        yield batch


COUNT_NAMES = ['count', 'cnt', 'number', 'num', '#', 'frequency', 'probability', 'prob', 'occurences']
def find_count_label(d):
    """Find the member of a set that means "count" or "frequency" or "probability" or "number of occurrences".

    """
    for name in COUNT_NAMES:
        if name in d:
            return name
    for name in COUNT_NAMES:
        if str(name).lower() in d:
            return name


def first_in_seq(seq):
    # lists/sequences
    return next(iter(seq))


def get_key_for_value(dict_obj, value, default=None):
    """
    >>> get_key_for_value({0: 'what', 'k': 'ever', 'you': 'want', 'to find': None}, 'you')
    >>> get_key_for_value({0: 'what', 'k': 'ever', 'you': 'want', 'to find': None}, 'you', default='Not Found')
    'Not Found'
    >>> get_key_for_value({0: 'what', 'k': 'ever', 'you': 'want', 'to find': None}, 'other', default='Not Found')
    'Not Found'
    >>> get_key_for_value({0: 'what', 'k': 'ever', 'you': 'want', 'to find': None}, 'want')
    'you'
    >>> get_key_for_value({0: 'what', '': 'ever', 'you': 'want', 'to find': None, 'you': 'too'}, 'what')
    0
    >>> get_key_for_value({0: 'what', '': 'ever', 'you': 'want', 'to find': None, 'you': 'too', ' ': 'want'}, 'want')
    ' '
    """
    for k, v in dict_obj.iteritems():
        if v == value:
            return k
    return default


def sod_transposed(seq_of_dicts, align=True, fill=True, filler=None):
    """Return sequence (list) of dictionaries, transposed into a dictionary of sequences (lists)
    
    >>> sorted(sod_transposed([{'c': 1, 'cm': u'P'}, {'c': 1, 'ct': 2, 'cm': 6, 'cn': u'MUS'}, {'c': 1, 'cm': u'Q', 'cn': u'ROM'}], filler=0).items())
    [('c', [1, 1, 1]), ('cm', [u'P', 6, u'Q']), ('cn', [0, u'MUS', u'ROM']), ('ct', [0, 2, 0])]
    >>> sorted(sod_transposed(({'c': 1, 'cm': u'P'}, {'c': 1, 'ct': 2, 'cm': 6, 'cn': u'MUS'}, {'c': 1, 'cm': u'Q', 'cn': u'ROM'}), fill=0, align=0).items())
    [('c', [1, 1, 1]), ('cm', [u'P', 6, u'Q']), ('cn', [u'MUS', u'ROM']), ('ct', [2])]
    """
    result = {}
    if isinstance(seq_of_dicts, Mapping):
        seq_of_dicts = [seq_of_dicts]
    it = iter(seq_of_dicts)
    # if you don't need to align and/or fill, then just loop through and return
    if not (align and fill):
        for d in it:
            for k in d:
                result[k] = result.get(k, []) + [d[k]]
        return result
    # need to align and/or fill, so pad as necessary
    for i, d in enumerate(it):
        for k in d:
            result[k] = result.get(k, [filler] * (i * int(align))) + [d[k]]
        for k in result:
            if k not in d:
                result[k] += [filler]
    return result


def joined_seq(seq, sep=None):
    """Join a sequence into a tuple or a concatenated string

    >>> joined_seq(range(3), ', ')
    '0, 1, 2'
    >>> joined_seq([1, 2, 3])
    (1, 2, 3)
    """
    joined_seq = tuple(seq)
    if isinstance(sep, basestring):
        joined_seq = sep.join(str(item) for item in joined_seq)
    return joined_seq


def consolidate_stats(dict_of_seqs, stats_key=None, sep=','):
    """Join (stringify and concatenate) keys (table fields) in a dict (table) of sequences (columns)

    >>> consolidate_stats(dict([('c', [1, 1, 1]), ('cm', [u'P', 6, u'Q']), ('cn', [0, u'MUS', u'ROM']), ('ct', [0, 2, 0])]), stats_key='c')
    [{'P,0,0': 1}, {'6,MUS,2': 1}, {'Q,ROM,0': 1}]
    >>> consolidate_stats([{'c': 1, 'cm': 'P', 'cn': 0, 'ct': 0}, {'c': 1, 'cm': 6, 'cn': 'MUS', 'ct': 2}, {'c': 1, 'cm': 'Q', 'cn': 'ROM', 'ct': 0}], stats_key='c')
    [{'P,0,0': 1}, {'6,MUS,2': 1}, {'Q,ROM,0': 1}]
    """
    if isinstance(dict_of_seqs, dict):
        stats = dict_of_seqs[stats_key]
        keys = joined_seq(sorted([k for k in dict_of_seqs if k is not stats_key]), sep=None)
        joined_key = joined_seq(keys, sep=sep)
        result = {stats_key: [], joined_key: []}
        for i, stat in enumerate(stats):
            result[stats_key] += [stat]
            result[joined_key] += [joined_seq((dict_of_seqs[k][i] for k in keys if k is not stats_key), sep)]
        return list({k: result[stats_key][i]} for i, k in enumerate(result[joined_key]))
    return [{joined_seq((d[k] for k in sorted(d) if k is not stats_key), sep): d[stats_key]} for d in dict_of_seqs]


def dos_from_table(table, header=None):
    """Produce dictionary of sequences from sequence of sequences, optionally with a header "row".

    >>> dos_from_table([['hello', 'world'], [1, 2], [3,4]]) == {'hello': [1, 3], 'world': [2, 4]}
    True
    """
    start_row = 0
    if not table:
        return table
    if not header:
        header = table[0]
        start_row = 1
    header_list = header
    if header and isinstance(header, basestring):
        header_list = header.split('\t')
        if len(header_list)!=len(table[0]):
            header_list = header.split(',')
        if len(header_list)!=len(table[0]):
            header_list = header.split(' ')
    ans = {}
    for i, k in enumerate(header):
        ans[k] = [row[i] for row in table[start_row:]]
    return ans


def transposed_lists(list_of_lists, default=None):
    """Like numpy.transposed, but allows for uneven row lengths

    Uneven lengths will affect the order of the elements in the rows of the transposed lists

    >>> transposed_lists([[1, 2], [3, 4, 5], [6]])
    [[1, 3, 6], [2, 4], [5]]
    >>> transposed_lists(transposed_lists([[], [1, 2, 3], [4]]))
    [[1, 2, 3], [4]]
    >>> l = transposed_lists([range(4),[4,5]])
    >>> l
    [[0, 4], [1, 5], [2], [3]]
    >>> transposed_lists(l)
    [[0, 1, 2, 3], [4, 5]]
    """
    if default is None or default is [] or default is tuple():
        default = []
    elif default is 'None':
        default = [None]
    else:
        default = [default]
    
    N = len(list_of_lists)
    Ms = [len(row) for row in list_of_lists]
    M = max(Ms)
    ans = []
    for j in range(M):
        ans += [[]]
        for i in range(N):
            if j < Ms[i]:
                ans[-1] += [list_of_lists[i][j]]
            else:
                ans[-1] += list(default)
    return ans


def transposed_matrix(matrix, filler=None, row_type=list, matrix_type=list, value_type=None):
    """Like numpy.transposed, evens up row (list) lengths that aren't uniform, filling with None.

    Also, makes all elements a uniform type (default=type(matrix[0][0])), 
    except for filler elements.

    TODO: add feature to delete None's at the end of rows so that transpose(transpose(LOL)) = LOL

    >>> transposed_matrix([[1, 2], [3, 4, 5], [6]])
    [[1, 3, 6], [2, 4, None], [None, 5, None]]
    >>> transposed_matrix(transposed_matrix([[1, 2], [3, 4, 5], [6]]))
    [[1, 2, None], [3, 4, 5], [6, None, None]]
    >>> transposed_matrix([[], [1, 2, 3], [4]])  # empty first row forces default value type (float)
    [[None, 1.0, 4.0], [None, 2.0, None], [None, 3.0, None]]
    >>> transposed_matrix(transposed_matrix([[], [1, 2, 3], [4]]))
    [[None, None, None], [1.0, 2.0, 3.0], [4.0, None, None]]
    >>> l = transposed_matrix([range(4),[4,5]])
    >>> l
    [[0, 4], [1, 5], [2, None], [3, None]]
    >>> transposed_matrix(l)
    [[0, 1, 2, 3], [4, 5, None, None]]
    >>> transposed_matrix([[1,2],[1],[1,2,3]])
    [[1, 1, 1], [2, None, 2], [None, None, 3]]
    """

    matrix_type = matrix_type or type(matrix)
    # matrix = matrix_type(matrix)

    try:
        row_type = row_type or type(matrix[0])
    except:
        pass
    if not row_type or row_type == type(None):
        row_type = list

    try:
        value_type = value_type or type(matrix[0][0]) or float
    except:
        pass
    if not value_type or value_type == type(None):
        value_type = float

    #print matrix_type, row_type, value_type

    # original matrix is NxM, new matrix will be MxN
    N = len(matrix)
    Ms = [len(row) for row in matrix]
    M = 0 if not Ms else max(Ms)

    ans = []
    # for each row in the new matrix (column in old matrix)
    for j in range(M):
        # add a row full of copies the `fill` value up to the maximum width required
        ans += [row_type([filler] * N)]
        for i in range(N):
            try:
                ans[j][i] = value_type(matrix[i][j])
            except IndexError:
                ans[j][i] = filler
            except TypeError:
                ans[j][i] = filler

    try:
        if isinstance(ans[0], row_type):
            return matrix_type(ans)
    except:
        pass
    return matrix_type([row_type(row) for row in ans])


def hist_from_values_list(values_list, fillers=(None,), normalize=False, cumulative=False, to_str=False, sep=',', min_bin=None, max_bin=None):
    """Compute an emprical histogram, PMF or CDF in a list of lists or a csv string

    Only works for discrete (integer) values (doesn't bin real values).
    `fillers`: list or tuple of values to ignore in computing the histogram

    >>> hist_from_values_list([1,1,2,1,1,1,2,3,2,4,4,5,7,7,9])  # doctest: +NORMALIZE_WHITESPACE
    [(1, 5),
     (2, 3),
     (3, 1),
     (4, 2),
     (5, 1),
     (6, 0),
     (7, 2),
     (8, 0),
     (9, 1)]
    >>> hist_from_values_list([(1,9),(1,8),(2,),(1,),(1,4),(2,5),(3,3),(5,0),(2,2)])  # doctest: +NORMALIZE_WHITESPACE
    [(0, 0, 1), (1, 4, 0), (2, 3, 1), (3, 1, 1), (4, 0, 1), (5, 1, 1), (6, 0, 0), (7, 0, 0), (8, 0, 1), (9, 0, 1)]
    >>> hist_from_values_list(transposed_matrix([(8,),(1,3,5),(2,),(3,4,5,8)]))  # doctest: +NORMALIZE_WHITESPACE
    [(1, 0, 1, 0, 0), (2, 0, 0, 1, 0), (3, 0, 1, 0, 1), (4, 0, 0, 0, 1), (5, 0, 1, 0, 1), (6, 0, 0, 0, 0), (7, 0, 0, 0, 0), (8, 1, 0, 0, 1)]
    """
    value_types = tuple([int] + [type(filler) for filler in fillers])
    if all(isinstance(value, value_types) for value in values_list):
        counters = [Counter(values_list)]
    elif all(len(row)==1 for row in values_list) and all(isinstance(row[0], value_types) for row in values_list):
        counters = [Counter(values[0] for values in values_list)]
    else:
        values_list_t = transposed_matrix(values_list)
        counters = [Counter(col) for col in values_list_t]

    if fillers:
        fillers = listify(fillers)
        for counts in counters:
            for ig in fillers:
                if ig in counts:
                    del counts[ig]

    intkeys_list = [[c for c in counts if (isinstance(c, int) or (isinstance(c, float) and int(c) == c))] for counts in counters]
    try:
        min_bin = int(min_bin)
    except:
        min_bin = min(min(intkeys) for intkeys in intkeys_list)
    try:
        max_bin = int(max_bin)
    except:
        max_bin = max(max(intkeys) for intkeys in intkeys_list)

    min_bin = max(min_bin, min((min(intkeys) if intkeys else 0) for intkeys in intkeys_list))  # TODO: reuse min(intkeys)
    max_bin = min(max_bin, max((max(intkeys) if intkeys else 0) for intkeys in intkeys_list))  # TODO: reuse max(intkeys)

    histograms = []
    for intkeys, counts in zip(intkeys_list, counters):
        histograms += [OrderedDict()]
        if not intkeys:
            continue
        if normalize:
            N = sum(counts[c] for c in intkeys)
            for c in intkeys:
                counts[c] = float(counts[c]) / N
        if cumulative:
            for i in xrange(min_bin, max_bin + 1):
                histograms[-1][i] = counts.get(i, 0) + histograms[-1].get(i-1, 0)
        else:
            for i in xrange(min_bin, max_bin + 1):
                histograms[-1][i] = counts.get(i, 0)
    if not histograms:
        histograms = [OrderedDict()]

    # fill in the zero counts between the integer bins of the histogram
    aligned_histograms = []

    for i in range(min_bin, max_bin + 1):
        aligned_histograms += [tuple([i] + [hist.get(i, 0) for hist in histograms])]

    if to_str:
        # FIXME: add header row
        return str_from_table(aligned_histograms, sep=sep, max_rows=365*2+1)

    return aligned_histograms


def update_dict(d, u, depth=-1, default_map=dict, default_set=set, prefer_update_type=False):
    """
    Recursively merge (union or update) dict-like objects (collections.Mapping) to the specified depth.

    >>> update_dict({'k1': {'k2': 2}}, {'k1': {'k2': {'k3': 3}}, 'k4': 4})
    {'k1': {'k2': {'k3': 3}}, 'k4': 4}
    >>> update_dict(OrderedDict([('k1', OrderedDict([('k2', 2)]))]), {'k1': {'k2': {'k3': 3}}, 'k4': 4})
    OrderedDict([('k1', OrderedDict([('k2', {'k3': 3})])), ('k4', 4)])
    >>> update_dict(OrderedDict([('k1', dict([('k2', 2)]))]), {'k1': {'k2': {'k3': 3}}, 'k4': 4})
    OrderedDict([('k1', {'k2': {'k3': 3}}), ('k4', 4)])
    """
    arg_types = (type(d), type(u))
    dictish = arg_types[int(prefer_update_type) % 2] if arg_types[int(prefer_update_type) % 2] is Mapping else default_map
    #settish = types[int(prefer_update_type) % 2] if types[int(prefer_update_type) % 2] is (set, list, tuple) else default_set
    for k, v in u.iteritems():
        if isinstance(v, Mapping) and not depth == 0:
            r = update_dict(d.get(k, dictish()), v, depth=max(depth - 1, -1))
            d[k] = r
        elif isinstance(d, Mapping):
            d[k] = u[k]
        else:
            d = dictish([(k, u[k])])
    return d


def mapped_transposed_lists(lists, default=None):
    """
    Swap rows and columns in list of lists with different length rows/columns

    Pattern from
    http://code.activestate.com/recipes/410687-transposing-a-list-of-lists-with-different-lengths/
    Replaces any zeros or Nones with default value.

    Examples:
    >>> l = mapped_transposed_lists([range(4),[4,5]],None)
    >>> l
    [[0, 4], [1, 5], [2, None], [3, None]]
    >>> mapped_transposed_lists(l)
    [[0, 1, 2, 3], [4, 5, None, None]]
    """
    if not lists:
        return []
    return map(lambda *row: [el if isinstance(el, (float, int)) else default for el in row], *lists)


def make_name(s, camel=None, lower=None, space='_', remove_prefix=None):
    """Process a string to produce a valid python variable/class/type name

    Useful for producing Django model names out of file names, or Django field names out of a csv file headers

    >>> make_name("PD / SZ")
    'pd_sz'
    """
    if camel is None and lower is None:
        lower = True
    if not s:
        return None
    s = str(s)  # TODO: encode in ASCII, UTF-8, or the charset used for this file!
    if remove_prefix and s.startswith(remove_prefix):
        s = s[len(remove_prefix):]
    if camel:
        if any(c in ' \t\n\r' + string.punctuation for c in s) or s.lower() == s:
            if lower:
                s = s.lower()
            s = s.title()
    elif lower:
        s = s.lower()
    if space is not None:
        escape = '\\' if space and space not in ' _' else ''
        s = re.sub('[^a-zA-Z0-9' + escape + space +']+', space, s)
        if space:
            s = re.sub('[' + escape + space + ']{2,}', space, s)
    return s
make_name.DJANGO_FIELD = {'camel': False, 'lower': True, 'space': '_'}
make_name.DJANGO_MODEL = {'camel': True, 'lower': False, 'space': '', 'remove_prefix': 'models'}


def tryconvert(value, desired_types=SCALAR_TYPES, default=None, empty='', strip=True):
    """
    Convert value to one of the desired_types specified (in order of preference) without raising an exception.

    If value is empty is a string and Falsey, then return the `empty` value specified.
    If value can't be converted to any of the desired_types requested, then return the `default` value specified.

    >>> tryconvert('MILLEN2000', desired_types=float, default='GENX')
    'GENX'
    >>> tryconvert('1.23', desired_types=[int,float], default='default')
    1.23
    >>> tryconvert('-1.0', desired_types=[int,float])  # assumes you want a float if you have a trailing .0 in a str
    -1.0
    >>> tryconvert(-1.0, desired_types=[int,float])  # assumes you want an int if int type listed first
    -1
    >>> repr(tryconvert('1+1', desired_types=[int,float]))
    'None'
    """
    if value in tryconvert.EMPTY:
        if isinstance(value, basestring):
            return type(value)(empty)
        return empty
    if isinstance(value, basestring):
        # there may not be any "empty" strings that won't be caught by the `is ''` check above, but just in case
        if not value:
            return type(value)(empty)
        if strip:
            value = value.strip()
    if isinstance(desired_types, type):
        desired_types = (desired_types,)
    if desired_types is not None and len(desired_types) == 0:
        desired_types = tryconvert.SCALAR
    if len(desired_types):
        if isinstance(desired_types, (list, tuple)) and len(desired_types) and isinstance(desired_types[0], (list, tuple)):
            desired_types = desired_types[0]
        elif isinstance(desired_types, (type)):
            desired_types = [desired_types]
    for t in desired_types:
        try:
            return t(value)
        except (ValueError, TypeError):
            continue
        # if any other weird exception happens then need to get out of here
        return default
    # if no conversions happened successfully then return the default value requested
    return default
tryconvert.EMPTY = ('', None, float('nan'))
tryconvert.SCALAR = SCALAR_TYPES


def read_csv(path, ext='.csv', verbose=False, format=None, delete_empty_keys=False,
             fieldnames=[], rowlimit=100000000, numbers=False, normalize_names=True, unique_names=True):
    """
    Read a csv file from the specified path, return a dict of lists or list of lists (according to `format`)

    filename: a directory or list of file paths
    numbers: whether to attempt to convert strings in csv to numbers
    """
    if not path:
        return

    if format:
        format = format[0].lower()
    recs = []
    # see http://stackoverflow.com/a/4169762/623735 before trying 'rU'
    with open(path, 'rUb') as fpin:  # U = universal EOL reader, b = binary
        # if fieldnames not specified then assume that first row of csv contains headings
        csvr = csv.reader(fpin, dialect=csv.excel)
        if not fieldnames:
            while not fieldnames or not any(fieldnames):
                fieldnames = csvr.next()
            if verbose:
                logger.info('Column Labels: ' + repr(fieldnames))
        if unique_names:
            norm_names = OrderedDict([(fldnm, fldnm) for fldnm in fieldnames])
        else:
            norm_names = OrderedDict([(num, fldnm) for num, fldnm in enumerate(fieldnames)])
        if normalize_names:
            norm_names = OrderedDict([(num, make_name(fldnm, **make_name.DJANGO_FIELD)) for num, fldnm in enumerate(fieldnames)])
            # required for django-formatted json files
            model_name = make_name(path, **make_name.DJANGO_MODEL)
        if format in ('c',):  # columnwise dict of lists
            recs = OrderedDict((norm_name, []) for norm_name in norm_names.values())
        if verbose:
            logger.info('Field Names: ' + repr(norm_names if normalize_names else fieldnames))
        rownum = 0
        eof = False
        pbar = None
        file_len = os.fstat(fpin.fileno()).st_size
        if verbose:
            pbar = ProgressBar(maxval=file_len)
            pbar.start()
        while csvr and rownum < rowlimit and not eof:
            if pbar:
                pbar.update(fpin.tell())
            rownum += 1
            row = []
            row_dict = OrderedDict()
            # skips rows with all empty strings as values,
            while not row or not any(len(x) for x in row):
                try:
                    row = csvr.next()
                    if verbose > 1:
                        logger.info('  row content: ' + repr(row))
                except StopIteration:
                    eof = True
                    break
            if eof:
                break
            if numbers:
                # try to convert the type to a numerical scalar type (int, float etc)
                row = [tryconvert(v, empty=None, default=v) for v in row]
            if row:
                N = min(max(len(row), 0), len(norm_names))
                row_dict = OrderedDict(((field_name, field_value) for field_name, field_value in zip(list(norm_names.values() if unique_names else norm_names)[:N], row[:N]) if (str(field_name).strip() or delete_empty_keys is False)))
                if format in ('d', 'j'):  # django json format
                    recs += [{"pk": rownum, "model": model_name, "fields": row_dict}]
                elif format in ('v',):  # list of values format
                    # use the ordered fieldnames attribute to keep the columns in order
                    recs += [[value for field_name, value in row_dict.iteritems() if (field_name.strip() or delete_empty_keys is False)]]
                elif format in ('c',):  # columnwise dict of lists
                    for field_name in row_dict:
                        recs[field_name] += [row_dict[field_name]]
                else:
                    recs += [row_dict]
        if file_len > fpin.tell():
            logger.info("Only %d of %d bytes were read." % (fpin.tell(), file_len))
        if pbar:
            pbar.finish()
    if not unique_names:
        return recs, norm_names
    return recs


def column_name_to_date(name):
    """
    TODO: should probably assume a 2000 epoch for 2-digit dates

    >>> column_name_to_date('10-Apr')
    datetime.date(10, 4, 1)
    >>> column_name_to_date('10_2011')
    datetime.date(2011, 10, 1)
    >>> column_name_to_date('apr_10')
    datetime.date(10, 4, 1)
    """
    month_nums = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
    year_month = re.split(r'[^0-9a-zA-Z]{1}', name)
    try:
        year = int(year_month[0])
        month = year_month[1]
    except:
        year = int(year_month[1])
        month = year_month[0]
    month = month_nums.get(str(month).lower().title(), None)
    if 0 <= year <= 2100 and 1 <= month <= 12:
        return datetime.date(year, month, 1)
    try:
        year = int(year_month[1])
        month = int(year_month[0])
    except:
        year. month = 0, 0
    if 0 <= year <= 2100 and 1 <= month <= 12:
        return datetime.date(year, month, 1)
    try:
        month = int(year_month[1])
        year = int(year_month[0])
    except:
        year. month = 0, 0
    if 0 <= year <= 2100 and 1 <= month <= 12:
        return datetime.date(year, month, 1)



def first_digits(s, default=0):
    """Return the fist (left-hand) digits in a string as a single integer, ignoring sign (+/-).
    >>> first_digits('+123.456')
    123
    """
    s = re.split(r'[^0-9]+', str(s).strip().lstrip('+-' + chars.whitespace))
    if len(s) and len(s[0]):
        return int(s[0])
    return default


def int_pair(s, default=(0, None)):
    """Return the digits to either side of a single non-digit character as a 2-tuple of integers

    >>> int_pair('90210-007')
    (90210, 7)
    >>> int_pair('04321.0123')
    (4321, 123)
    """
    s = re.split(r'[^0-9]+', str(s).strip())
    if len(s) and len(s[0]):
        if len(s) > 1 and len(s[1]):
            return (int(s[0]), int(s[1]))
        return (int(s[0]), default[1])
    return default


def make_us_postal_code(s, allowed_lengths=(), allowed_digits=()):
    """
    >>> make_us_postal_code(1234)
    '01234'
    >>> make_us_postal_code(507.6009)
    '507'
    >>> make_us_postal_code(90210.0)
    '90210'
    >>> make_us_postal_code(39567.7226)
    '39567-7226'
    >>> make_us_postal_code(39567.7226)
    '39567-7226'
    """
    allowed_lengths = allowed_lengths or tuple(N if N < 6 else N + 1 for N in allowed_digits)
    allowed_lengths = allowed_lengths or (2, 3, 5, 10)
    ints = int_pair(s)
    z = str(ints[0]) if ints[0] else ''
    z4 = '-' + str(ints[1]) if ints[1] else ''
    if len(z) == 4:
        z = '0' + z
    if len(z + z4) in allowed_lengths:
        return z + z4
    elif len(z) in (min(l, 5) for l in allowed_lengths):
        return z
    return ''

# TODO: create and check MYSQL_MAX_FLOAT constant
def make_float(s, default='', ignore_commas=True):
    r"""Coerce a string into a float

    >>> make_float('12.345')
    12.345
    >>> make_float('1+2')
    3.0
    >>> make_float('+42.0')
    42.0
    >>> make_float('\r\n-42?\r\n')
    -42.0
    >>> make_float('$42.42')
    42.42
    >>> make_float('B-52')
    -52.0
    >>> make_float('1.2 x 10^34')
    1.2e+34
    >>> make_float(float('nan'))
    nan
    >>> make_float(float('-INF'))
    -inf
    """
    if ignore_commas and isinstance(s, basestring):
        s = s.replace(',', '')
    try:
        return float(s)
    except:
        try:
            return float(str(s))
        except ValueError:
            try:
                return float(normalize_scientific_notation(str(s), ignore_commas))
            except ValueError:
                try:
                    return float(first_digits(s))
                except ValueError:
                    return default


# TODO: create and check MYSQL_MAX_FLOAT constant
def make_int(s, default='', ignore_commas=True):
    r"""Coerce a string into an integer (long ints will fail)

    TODO:
    - Ignore dashes and other punctuation within a long string of digits,
       like a telephone number, partnumber, datecode or serial number.
    - Use the Decimal type to allow infinite precision

    >>> make_int('12345')
    12345
    >>> make_int('0000012345000       ')
    12345000
    """
    if ignore_commas and isinstance(s, basestring):
        s = s.replace(',', '')
    try:
        return int(s)
    except:
        try:
            return int(re.split(str(s), '[^-0-9,.Ee]')[0])
        except ValueError:
            try:
                return int(float(normalize_scientific_notation(str(s), ignore_commas)))
            except (ValueError, TypeError):
                try:
                    return int(first_digits(s))
                except (ValueError, TypeError):
                    return default


# FIXME: use locale and/or check that they occur ever 3 digits (1000's places) to decide whether to ignore commas
def normalize_scientific_notation(s, ignore_commas=True):
    """Produce a string convertable with float(s), if possible, fixing some common scientific notations

    Deletes commas and allows addition.
    >>> normalize_scientific_notation(' -123 x 10^-45 ')
    '-123e-45'
    >>> normalize_scientific_notation(' -1+1,234 x 10^-5,678 ')
    '1233e-5678'
    >>> normalize_scientific_notation('$42.42')
    '42.42'
    """
    s = s.lstrip(chars.not_digits_nor_sign)
    s = s.rstrip(chars.not_digits)
    #print s
    # TODO: substitute ** for ^ and just eval the expression rather than insisting on a base-10 representation
    num_strings = rep.scientific_notation_exponent.split(s, maxsplit=2)
    #print num_strings
    # get rid of commas
    s = rep.re.sub(r"[^.0-9-+" + "," * int(not ignore_commas) + r"]+", '', num_strings[0])
    #print s
    # if this value gets so large that it requires an exponential notation, this will break the conversion
    if not s:
        return None
    try:
        s = str(eval(s))
    except:
        print 'Unable to evaluate %s' % repr(s)
        try:
            s = str(float(s))
        except:
            print 'Unable to float %s' % repr(s)
            s = ''
    #print s
    if len(num_strings) > 1:
        if not s:
            s = '1'
        s += 'e' + rep.re.sub(r'[^.0-9-+]+', '', num_strings[1])
    if s:
        return s
    return None


def normalize_serial_number(sn, max_length=10, left_fill='0', right_fill='', blank='', valid_chars='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ -', invalid_chars=None, join=False):
    r"""Make a string compatible with typical serial number requirements

    >>> normalize_serial_number('1C 234567890             ', valid_chars='0123456789')
    '0234567890'
    >>> normalize_serial_number('1C 234567890             ')
    '1C 0234567890'
    >>> normalize_serial_number(' \t1C\t-\t234567890 \x00\x7f', max_length=14, left_fill='0', valid_chars='0123456789ABC', invalid_chars=None, join=True)
    '0001C234567890'
    >>> normalize_serial_number('Unknown', blank=False)
    '0000000000'
    >>> normalize_serial_number('Unknown', blank=None)
    >>> normalize_serial_number('N/A', blank='')
    ''
    >>> normalize_serial_number('NO SERIAL', blank='----------')  # doctest: +NORMALIZE_WHITESPACE
    '----------' 
    """
    # strip internal and external whitespace and consider only last 10 characters
    if invalid_chars is None:
        invalid_chars = (c for c in ascii.all_ if c not in valid_chars)
    invalid_chars = ''.join(invalid_chars)
    sn = str(sn).strip(invalid_chars)
    if invalid_chars:
        if join:
            sn = sn.translate(None, invalid_chars)
        else:
            sn = multisplit(sn, invalid_chars)[-1]
    sn = sn[-max_length:]
    if not sn and not (blank is False):
        return blank
    if left_fill:
        sn = left_fill * (max_length - len(sn)/len(left_fill)) + sn
    if right_fill:
        sn = sn + right_fill * (max_length - len(sn)/len(right_fill))
    return sn


def multisplit(s, seps=list(string.punctuation) + list(string.whitespace), blank=True):
    r"""Just like str.split(), except that a variety (list) of seperators is allowed.
    
    >>> multisplit(r'1-2?3,;.4+-', string.punctuation)
    ['1', '2', '3', '', '', '4', '', '']
    >>> multisplit(r'1-2?3,;.4+-', string.punctuation, blank=False)
    ['1', '2', '3', '4']
    """
    seps = ''.join(seps)
    return [s2 for s2 in s.translate(''.join([(chr(i) if chr(i) not in seps else seps[0]) for i in range(256)])).split(seps[0]) if (blank or s2)]


def make_real(list_of_lists):
    for i, l in enumerate(list_of_lists):
        for j, val in enumerate(l):
            list_of_lists[i][j] = float(normalize_scientific_notation(str(val), ignore_commas=True))
    return list_of_lists


def linear_correlation(x, y=None, ddof=0):
    """Pierson linear correlation coefficient (-1 <= plcf <= +1)
    >>> abs(linear_correlation(range(5), [1.2 * x + 3.4 for x in range(5)]) - 1.0) < 0.000001
    True
    >>> abs(linear_correlation(sci.rand(2, 1000)))  # doctest: +ELLIPSIS, +NORMALIZE_WHITESPACE
    0.0...
    """
    if y is None:
        if len(x) == 2:
            y = x[1]
            x = x[0]
        elif len(x[0]) ==2:
            y = [yi for xi, yi in x] 
            x = [xi for xi, yi in x]
        else:
            mat = np.cov(x, ddof=ddof)
            R = []
            N = len(mat)
            for i in range(N):
                R += [[1.] * N]
                for j in range(i+1,N):
                    R[i][j] = mat[i,j]
                    for k in range(N):
                        R[i][j] /= (mat[k,k] ** 0.5)
            return R
    return np.cov(x, y, ddof=ddof)[1,0] / np.std(x, ddof=ddof) / np.std(y, ddof=ddof)


def best_correlation_offset(x, y, ddof=0):
    """Find the delay between x and y that maximizes the correlation between them
    A negative delay means a negative-correlation between x and y was maximized
    """
    def offset_correlation(offset, x=x, y=y):
        N = len(x)
        if offset < 0:
            y = [-1 * yi for yi in y]
            offset = -1 * offset 
        # TODO use interpolation to allow noninteger offsets
        return linear_correlation([x[(i - int(offset)) % N] for i in range(N)], y)
    return sci.minimize(offset_correlation, 0)


def imported_modules():
    for name, val in globals().items():
        if isinstance(val, types.ModuleType):
            yield val


def make_tz_aware(dt, tz='UTC'):
    """Add timezone information to a datetime object, only if it is naive."""
    tz = dt.tzinfo or tz
    try:
        tz = pytz.timezone(tz)
    except AttributeError:
        pass
    return tz.localize(dt)


def clean_wiki_datetime(dt, squelch=False):
    if isinstance(dt, datetime.datetime):
        return dt
    elif not isinstance(dt, basestring):
        dt = ' '.join(dt)
    try:
        return make_tz_aware(dateutil.parser.parse(dt))
    except:
        if not squelch:
            print("Failed to parse %r" % dt)
    dt = [s.strip() for s in dt.split(' ')]
    # get rid of any " at " or empty strings
    dt = [s for s in dt if s and s.lower() != 'at']

    # deal with the absence of :'s in wikipedia datetime strings

    if RE_MONTH_NAME.match(dt[0]) or RE_MONTH_NAME.match(dt[1]):
        if len(dt) >= 5:
            dt = dt[:-2] + [dt[-2].strip(':') + ':' + dt[-1].strip(':')]
            return clean_wiki_datetime(' '.join(dt))
        elif len(dt) == 4 and (len(dt[3]) == 4 or len(dt[0]) == 4):
            dt[:-1] + ['00']
            return clean_wiki_datetime(' '.join(dt))
    elif RE_MONTH_NAME.match(dt[-2]) or RE_MONTH_NAME.match(dt[-3]):
        if len(dt) >= 5:
            dt = [dt[0].strip(':') + ':' + dt[1].strip(':')] + dt[2:]
            return clean_wiki_datetime(' '.join(dt))
        elif len(dt) == 4 and (len(dt[-1]) == 4 or len(dt[-3]) == 4):
            dt = [dt[0], '00'] + dt[1:]
            return clean_wiki_datetime(' '.join(dt))

    try:
        return make_tz_aware(dateutil.parser.parse(' '.join(dt)))
    except Exception as e:
        if squelch:
            from traceback import format_exc
            print format_exc(e) +  '\n^^^ Exception caught ^^^\nWARN: Failed to parse datetime string %r\n      from list of strings %r' % (' '.join(dt), dt)
            return dt
        raise(e)


def minmax_len_and_blackwhite_list(s, min_len=1, max_len=256, blacklist=None, whitelist=None, lower=False):
    if min_len > len(s) or len(s) > max_len:
        return False
    if lower:
        s = s.lower()
    if blacklist and s in blacklist:
        return False
    if whitelist and s not in whitelist:
        return False
    return True


def strip_HTML(s):
    """Simple, clumsy, slow HTML tag stripper"""
    result = ''
    total = 0
    for c in s:
        if c == '<':
            total = 1
        elif c == '>':
            total = 0
            result += ' '
        elif total == 0:
            result += c
    return result


def strip_edge_punc(s, punc=None, lower=None, str_type=str):
    if lower is None:
        lower = strip_edge_punc.lower
    if punc is None:
        punc = strip_edge_punc.punc
    if lower:
        s = s.lower()
    if not isinstance(s, basestring):
        return [strip_edge_punc(str_type(s0), punc) for s0 in s]
    return s.strip(punc)
strip_edge_punc.lower = False
strip_edge_punc.punc = PUNC


def get_sentences(s, regex=RE_SENTENCE_SPLIT):
    if isinstance(regex, basestring):
        regex = re.compile(regex)
    return [sent for sent in regex.split(s) if sent]


# this regex assumes "s' " is the end of a possessive word and not the end of an inner quotation, e.g. He said, "She called me 'Hoss'!"
def get_words(s, splitter_regex=RE_WORD_SPLIT_IGNORE_EXTERNAL_APOSTROPHIES, 
              preprocessor=strip_HTML, postprocessor=strip_edge_punc, min_len=None, max_len=None, blacklist=None, whitelist=None, lower=False, filter_fun=None, str_type=str):
    r"""Segment words (tokens), returning a list of all tokens (but not the separators/punctuation)

    >>> get_words('He said, "She called me \'Hoss\'!". I didn\'t hear.')
    ['He', 'said', 'She', 'called', 'me', 'Hoss', 'I', "didn't", 'hear']
    >>> get_words('The foxes\' oh-so-tiny den was 2empty!')
    ['The', 'foxes', 'oh-so-tiny', 'den', 'was', '2empty']
    """
    # TODO: Get rid of lower kwarg (and make sure code that uses it doesn't break) 
    #       That and other simple postprocessors can be done outside of get_words
    postprocessor = postprocessor or str_type
    preprocessor = preprocessor or str_type
    if min_len is None:
        min_len = get_words.min_len
    if max_len is None:
        max_len = get_words.max_len
    blacklist = blacklist or get_words.blacklist
    whitelist = whitelist or get_words.whitelist
    filter_fun = filter_fun or get_words.filter_fun
    lower = lower or get_words.lower
    try:
        s = open(s, 'r')
    except:
        pass
    try:
        s = s.read()
    except:
        pass
    if not isinstance(s, basestring):
        try:
            # flatten the list of lists of words from each obj (file or string)
            return [word for obj in s for word in get_words(obj)]
        except:
            pass
    try:
        s = preprocessor(s)
    except:
        pass
    if isinstance(splitter_regex, basestring):
        splitter_regex = re.compile(splitter_regex)
    s = map(postprocessor, splitter_regex.split(s))
    s = map(str_type, s)
    if not filter_fun:
        return s
    return [word for word in s if filter_fun(word, min_len=min_len, max_len=max_len, blacklist=blacklist, whitelist=whitelist, lower=lower)]
get_words.blacklist = ('', None, '\'', '.', '_', '-')
get_words.whitelist = None
get_words.min_len = 1
get_words.max_len = 256
get_words.lower = False
get_words.filter_fun = minmax_len_and_blackwhite_list


def pluralize_field_name(names=None, retain_prefix=False):
    if not names:
        return ''
    elif isinstance(names, basestring):
        if retain_prefix:
            split_name = names
        else:
            split_name = names.split('__')[-1]
        if not split_name:
            return names
        elif 0 < len(split_name) < 4 or split_name.lower()[-4:] not in ('call', 'sale', 'turn'):
            return split_name
        else:
            return split_name + 's'
    else:
        return [pluralize_field_name(name) for name in names]
pluralize_field_names = pluralize_field_name


def tabulate(lol, headers, eol='\n'):
    """Use the pypi tabulate package instead!"""
    yield '| %s |' % ' | '.join(headers) + eol
    yield '| %s:|' % ':| '.join(['-'*len(w) for w in headers]) + eol
    for row in lol:
        yield '| %s |' % '  |  '.join(str(c) for c in row) + eol


def intify(obj):
    """
    Return an integer that is representative of a categorical object (string, dict, etc)

    >>> intify('1.2345e10')
    12345000000
    >>> intify([12]), intify('[99]'), intify('(12,)')
    (91, 91, 40)
    >>> intify('A'), intify('B'), intify('b')
    (97, 98, 98)
    >>> intify(272)
    272
    """
    try:
        return int(float(obj))
    except:
        try:
            return ord(str(obj)[0].lower())
        except:
            try:
                return len(obj)
            except:
                try:
                    return hash(str(obj))
                except:
                    return 0


def listify(values, N=1, delim=None):
    """Return an N-length list, with elements values, extrapolating as necessary.

    >>> listify("don't split into characters")
    ["don't split into characters"]
    >>> listify("len = 3", 3)
    ['len = 3', 'len = 3', 'len = 3']
    >>> listify("But split on a delimeter, if requested.", delim=',')
    ['But split on a delimeter', ' if requested.']
    >>> listify(["obj 1", "obj 2", "len = 4"], N=4)
    ['obj 1', 'obj 2', 'len = 4', 'len = 4']
    >>> listify(iter("len=7"), N=7)
    ['l', 'e', 'n', '=', '7', '7', '7']
    >>> listify(iter("len=5"))
    ['l', 'e', 'n', '=', '5']
    >>> listify(None, 3)
    [[], [], []]
    >>> listify([None],3)
    [None, None, None]
    >>> listify([], 3)
    [[], [], []]
    >>> listify('', 2)
    ['', '']
    >>> listify(0)
    [0]
    >>> listify(False, 2)
    [False, False]
    """
    ans = [] if values is None else values

    # convert non-string non-list iterables into a list
    if hasattr(ans, '__iter__') and not isinstance(values, basestring):
        ans = list(ans)
    else:
        # split the string (if possible)
        if isinstance(delim, basestring):
            try:
                ans = ans.split(delim)
            except:
                ans = [ans]
        else:
            ans = [ans]

    # pad the end of the list if a length has been specified
    if len(ans):
        if len(ans) < N and N > 1:
            ans += [ans[-1]] * (N - len(ans))
    else:
        if N > 1:
            ans = [[]] * N

    return ans


def unlistify(l, depth=1, typ=list, get=None):
    """Return the desired element in a list ignoring the rest.

    >>> unlistify([1,2,3])
    1
    >>> unlistify([1,[4, 5, 6],3], get=1)
    [4, 5, 6]
    >>> unlistify([1,[4, 5, 6],3], depth=2, get=1)
    5
    >>> unlistify([1,(4, 5, 6),3], depth=2, get=1)
    (4, 5, 6)
    >>> unlistify([1,2,(4, 5, 6)], depth=2, get=2)
    (4, 5, 6)
    >>> unlistify([1,2,(4, 5, 6)], depth=2, typ=(list, tuple), get=2)
    6
    """
    i = 0
    if depth is None:
        depth = 1
    index_desired = get or 0
    while i < depth and isinstance(l, typ):
        if len(l):
            if len(l) > index_desired:
                l = l[index_desired]
                i += 1
        else:
            return l
    return l


def is_ignorable_str(s, ignorable_strings=(), lower=True, filename=True, startswith=True):
    ignorable_strings = listify(ignorable_strings)
    if not (lower or filename or startswith):
        return s in ignorable_strings
    for ignorable in ignorable_strings:
        if lower:
            ignorable = ignorable.lower()
            s = s.lower()
        if filename:
            s = s.split(os.path.sep)[-1]
        if startswith and s.startswith(ignorable):
            return True
        elif s == ignorable:
            return True


def strip_keys(d, nones=False, depth=0):
    r"""Strip whitespace from all dictionary keys, to the depth indicated

    >>> strip_keys({' a': ' a', ' b\t c ': {'d e  ': 'd e  '}}) == {'a': ' a', 'b\t c': {'d e  ': 'd e  '}}
    True
    >>> strip_keys({' a': ' a', ' b\t c ': {'d e  ': 'd e  '}}, depth=100) == {'a': ' a', 'b\t c': {'d e': 'd e  '}}
    True
    """
    ans = type(d)((str(k).strip(), v) for (k, v) in OrderedDict(d).iteritems() if (not nones or (str(k).strip() and str(k).strip() != 'None')))
    if int(depth) < 1:
        return ans
    if int(depth) > strip_keys.MAX_DEPTH:
        warnings.warn(RuntimeWarning("Maximum recursion depth allowance (%r) exceeded." % strip_keys.MAX_DEPTH))
    for k, v in ans.iteritems():
        if isinstance(v, Mapping):
            ans[k] = strip_keys(v, nones=nones, depth=int(depth)-1)
    return ans
strip_keys.MAX_DEPTH = 1e6


def str_from_table(table, sep='\t', eol='\n', max_rows=100000000, max_cols=1000000):
    max_rows = min(max_rows, len(table))
    return eol.join([sep.join(list(str(field) for field in row[:max_cols])) for row in table[:max_rows]])


def get_table_from_csv(filename='ssg_report_aarons_returns.csv', delimiter=',', dos=False):
    """Dictionary of sequences from CSV file"""
    table = []
    with open(filename, 'rb') as f:
        reader = csv.reader(f, dialect='excel', delimiter=delimiter)
        for row in reader:
            table += [row]
    if not dos:
        return table
    return dos_from_table(table)


def save_sheet(table, filename, ext='tsv', verbosity=0):
    if ext.lower() == 'tsv':
        sep = '\t'
    else:
        sep = ','
    s = str_from_table(table, sep=sep)
    if verbosity > 2:
        print s
    if verbosity:
        print 'Saving ' + filename + '.' + ext
    with open(filename + '.' + ext, 'w') as fpout:
        fpout.write(s)


def save_sheets(tables, filename, ext='.tsv', verbosity=0):
    for i, table in enumerate(tables):
        save_sheet(table, filename + '_Sheet%d' % i, ext=ext, verbosity=verbosity)



def shorten(s, max_length=16):
    """Attempt to shorten a phrase by deleting words at the end of the phrase

    >>> shorten('Hello World!')
    'Hello World'
    >>> shorten("Hello World! I'll talk your ear off!", 15)
    'Hello World'
    """
    short = s
    words = [abbreviate(word) for word in get_words(s)]
    for i in xrange(len(words), 0, -1):
        short = ' '.join(words[:i])
        if len(short) <= max_length:
            break
    return short[:max_length]


def abbreviate(word):
    return abbreviate.words.get(word, word)
abbreviate.words = {'account': 'acct', 'number': 'num', 'customer': 'cust', 'member': 'membr' }

