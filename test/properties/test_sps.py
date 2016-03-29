# Copyright (c) 2014, 2015 MIT Probabilistic Computing Project.
#
# This file is part of Venture.
#
# Venture is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Venture is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Venture.  If not, see <http://www.gnu.org/licenses/>.

# Testing the (Python) SP objects standalone

import math
import random
import numpy.random as npr
from testconfig import config
from nose.tools import eq_, assert_almost_equal
from flaky import flaky

from venture.test.config import gen_in_backend
from venture.test.randomized import * # Importing many things, which are closely related to what this is trying to do pylint: disable=wildcard-import, unused-wildcard-import
from venture.lite.builtin import builtInSPsIter
from venture.lite.psp import NullRequestPSP
from venture.lite.sp import VentureSPRecord
from venture.lite.utils import FixedRandomness

blacklist = ['make_csp', 'apply_function', 'make_gp',
             # TODO Appropriately construct random inputs to test
             # record constructors and accessors?
             'inference_action', 'action_func',
             'make_ref', 'ref_get']

# Select particular SPs to test thus:
# nosetests --tc=relevant:'["foo", "bar", "baz"]'
def relevantSPs():
  for (name,sp) in builtInSPsIter():
    if isinstance(sp.requestPSP, NullRequestPSP):
      if "relevant" not in config or config["relevant"] is None or name in config["relevant"]:
        if name not in blacklist: # Placeholder for selecting SPs to do or not do
          yield name, sp

@gen_in_backend("none")
def testTypes():
  for (name,sp) in relevantSPs():
    yield checkTypeCorrect, name, sp

def checkTypeCorrect(_name, sp):
  type_ = sp.venture_type()
  checkTypedProperty(propTypeCorrect, fully_uncurried_sp_type(type_), sp, type_)

def propTypeCorrect(args_lists, sp, type_):
  """Check that the successive return values of the given SP (when
applied fully uncurried) match the expected types."""
  if len(args_lists) == 0:
    pass # OK
  else:
    if isinstance(sp, VentureSPRecord):
      sp, aux = sp.sp, sp.spAux
    else:
      aux = carefully(sp.constructSPAux)
    args = BogusArgs(args_lists[0], aux)
    answer = carefully(sp.outputPSP.simulate, args)
    assert answer in type_.return_type
    propTypeCorrect(args_lists[1:], answer, type_.return_type)

@gen_in_backend("none")
def testDeterministic():
  for (name,sp) in relevantSPs():
    if name.startswith('gp_cov_') or name.startswith('gp_mean_'):
      # XXX Can't compare equivalent functions for equality without
      # false negatives.
      continue
    if not sp.outputPSP.isRandom():
      yield checkDeterministic, name, sp

def checkDeterministic(name, sp):
  checkTypedProperty(propDeterministic, fully_uncurried_sp_type(sp.venture_type()), name, sp)

def propDeterministic(args_lists, name, sp):
  """Check that the given SP returns the same answer every time (applied
fully uncurried)."""
  args = BogusArgs(args_lists[0], sp.constructSPAux())
  answer = carefully(sp.outputPSP.simulate, args)
  if isinstance(answer, VentureSPRecord):
    if isinstance(answer.sp.requestPSP, NullRequestPSP):
      if not answer.sp.outputPSP.isRandom():
        # We don't currently have any curried SPs that are
        # deterministic at both points, so this code never actually
        # runs.
        args2 = BogusArgs(args_lists[1], answer.spAux)
        ans2 = carefully(answer.sp.outputPSP.simulate, args2)
        for _ in range(5):
          new_ans = carefully(sp.outputPSP.simulate, args)
          new_ans2 = carefully(new_ans.sp.outputPSP.simulate, args2)
          eq_(ans2, new_ans2)
      else:
        raise SkipTest("Putatively deterministic sp %s returned a random SP" % name)
    else:
      raise SkipTest("Putatively deterministic sp %s returned a requesting SP" % name)
  else:
    for _ in range(5):
      eq_(answer, carefully(sp.outputPSP.simulate, args))

@gen_in_backend("none")
def testRandom():
  for (name,sp) in relevantSPs():
    if sp.outputPSP.isRandom():
      if name in ["make_uc_dir_cat", "categorical", "make_uc_sym_dir_cat",
                  "log_bernoulli", "log_flip",  # Because the default distribution does a bad job of picking arguments at which log_bernoulli's output actually varies.
                  "exactly" # Because it intentionally pretends to be random even though it's not.
      ]:
        continue
      elif name in ["inv_wishart"]:
        yield checkFlakyRandom, name, sp
      else:
        yield checkRandom, name, sp

def checkRandom(name, sp):
  py_rng = random.Random()
  np_rng = npr.RandomState()

  # Generate five approprite input/output pairs for the sp
  args_type = fully_uncurried_sp_type(sp.venture_type())
  def f(args_lists):
    return simulate_fully_uncurried(name, sp, args_lists, py_rng, np_rng)
  answers = [findAppropriateArguments(f, args_type, 30) for _ in range(5)]

  # Check that it returns different results on repeat applications to
  # at least one of the inputs.
  for answer in answers:
    if answer is None: continue # Appropriate input was not found; skip
    [args, ans, _] = answer
    for _ in range(10):
      ans2 = simulate_fully_uncurried(name, sp, args, py_rng, np_rng)
      if not ans2 == ans:
        return True # Output differed on some input: pass

  assert False, "SP deterministically gave i/o pairs %s" % answers

@flaky
def checkFlakyRandom(name, sp):
  checkRandom(name, sp)

def simulate_fully_uncurried(name, sp, args_lists, py_rng, np_rng):
  if isinstance(sp, VentureSPRecord):
    sp, aux = sp.sp, sp.spAux
  else:
    aux = carefully(sp.constructSPAux)
  if not isinstance(sp.requestPSP, NullRequestPSP):
    raise SkipTest("SP %s returned a requesting SP" % name)
  args = BogusArgs(args_lists[0], aux, py_rng, np_rng)
  answer = carefully(sp.outputPSP.simulate, args)
  if len(args_lists) == 1:
    return answer
  else:
    return simulate_fully_uncurried(name, answer, args_lists[1:], py_rng,
      np_rng)

def log_density_fully_uncurried(name, sp, args_lists, value):
  if isinstance(sp, VentureSPRecord):
    sp, aux = sp.sp, sp.spAux
  else:
    aux = carefully(sp.constructSPAux)
  if not isinstance(sp.requestPSP, NullRequestPSP):
    raise SkipTest("SP %s returned a requesting SP" % name)
  args = BogusArgs(args_lists[0], aux)
  if len(args_lists) == 1:
    return carefully(sp.outputPSP.logDensity, value, args)
  else:
    # TODO Is there a good general interface to
    # log_density_fully_uncurried that would let the client put in
    # this check?
    if sp.outputPSP.isRandom():
      raise SkipTest("The log density of the result of random curried SP %s is not actually deterministic" % name)
    answer = carefully(sp.outputPSP.simulate, args)
    return log_density_fully_uncurried(name, answer, args_lists[1:], value)

@gen_in_backend("none")
def testLogDensityDeterministic():
  for (name,sp) in relevantSPs():
    if name not in ["dict", "multivariate_normal", "wishart", "inv_wishart",  # TODO
                    "categorical", "make_dir_cat", "make_sym_dir_cat"]: # Only interesting when the presented value was among the inputs
      yield checkLogDensityDeterministic, name, sp

def checkLogDensityDeterministic(name, sp):
  checkTypedProperty(propLogDensityDeterministic, (fully_uncurried_sp_type(sp.venture_type()), final_return_type(sp.venture_type())), name, sp)

def propLogDensityDeterministic(rnd, name, sp):
  (args_lists, value) = rnd
  answer = log_density_fully_uncurried(name, sp, args_lists, value)
  if math.isnan(answer):
    raise ArgumentsNotAppropriate("Log density turned out to be NaN")
  for _ in range(5):
    eq_(answer, log_density_fully_uncurried(name, sp, args_lists, value))

@gen_in_backend("none")
def testFixingRandomness():
  for (name,sp) in relevantSPs():
    if name.startswith('gp_cov_') or name.startswith('gp_mean_'):
      # XXX Can't compare equivalent functions for equality without
      # false negatives.
      continue
    yield checkFixingRandomness, name, sp

def checkFixingRandomness(name, sp):
  checkTypedProperty(propDeterministicWhenFixed, fully_uncurried_sp_type(sp.venture_type()), name, sp)

def propDeterministicWhenFixed(args_lists, name, sp):
  py_rng = random.Random()
  np_rng = npr.RandomState()
  randomness = FixedRandomness(py_rng, np_rng)
  with randomness:
    answer = simulate_fully_uncurried(name, sp, args_lists, py_rng, np_rng)
  for _ in range(5):
    with randomness:
      answer_ = simulate_fully_uncurried(name, sp, args_lists, py_rng, np_rng)
      eq_(answer, answer_)
