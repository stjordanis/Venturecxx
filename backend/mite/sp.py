from __future__ import print_function

from venture.lite.request import Request, ESR
from venture.lite.sp import SPAux

class StochasticProcedure(object):
    def apply(self, args, constraint):
        raise NotImplementedError

    def unapply(self, value, args, constraint):
        raise NotImplementedError

    def simulate(self, args):
        raise NotImplementedError

    def logp(self, value, args):
        raise NotImplementedError

    def incorporate(self, value, args):
        pass

    def unincorporate(self, value, args):
        pass

    def request(self, args, constraint):
        raise NotImplementedError

    # for backward compatibility with existing implementation
    def constructSPAux(self): return SPAux()
    def hasAEKernel(self): return False
    def show(self, _spaux): return '<SP>'

class SimpleRandomSP(StochasticProcedure):
    def apply(self, args, constraint):
        if constraint is not None:
            value = constraint
            weight = self.logp(value, args)
        else:
            value = self.simulate(args)
            weight = 0.
        self.incorporate(value, args)
        return value, weight

    def unapply(self, value, args, constraint):
        self.unincorporate(value, args)
        if constraint is not None:
            weight = -self.logp(value, args)
        else:
            weight = 0.
        return weight

class SimpleLikelihoodFreeSP(StochasticProcedure):
    def apply(self, args, constraint):
        assert constraint is None
        value = self.simulate(args)
        weight = 0.
        self.incorporate(value, args)
        return value, weight

    def unapply(self, value, args, constraint):
        assert constraint is None
        self.unincorporate(value, args)
        weight = 0.
        return weight

LiteESR = ESR
class ESR(LiteESR):
    def __init__(self, id, exp, addr, env, constraint=None):
        self.id = id
        self.exp = exp
        self.addr = addr
        self.env = env
        self.constraint = constraint
1
class SimpleRequestingSP(StochasticProcedure):
    def apply(self, args, constraint):
        esr = self.request(args, constraint)
        req = Request([esr])
        return (req, self.cont, self.uncont), 0

    def cont(self, request, args, constraint):
        [value] = args.esrValues()
        return value, 0

    def uncont(self, request, args, constraint):
        return 0

    def unapply(self, value, args, constraint):
        return 0

class SimpleArgsWrapper(object):
    def __init__(self, operandValues, spaux=None, ripl=None, requesters=None):
        self._operandValues = operandValues
        self._spaux = spaux
        self._ripl = ripl
        self._requesters = requesters
        self.node = self
        self.env = None

    def operandValues(self):
        return self._operandValues

    def spaux(self):
        return self._spaux

class SimpleSPWrapper(StochasticProcedure):
    def __init__(self, outputPSP):
        self.outputPSP = outputPSP

    def simulate(self, args):
        return self.outputPSP.simulate(args)

    def logp(self, value, args):
        return self.outputPSP.logDensity(value, args)

    def incorporate(self, value, args):
        return self.outputPSP.incorporate(value, args)

    def unincorporate(self, value, args):
        return self.outputPSP.unincorporate(value, args)

class SimpleRandomSPWrapper(SimpleSPWrapper, SimpleRandomSP):
    pass

class SimpleDeterministicSPWrapper(SimpleSPWrapper, SimpleLikelihoodFreeSP):
    pass

from venture.lite.psp import DeterministicPSP, TypedPSP
import venture.lite.types as t
from venture.lite.sp import VentureSPRecord, SPType
from venture.lite.env import VentureEnvironment

# copied from csp.py, modified to return a new-style SP
class MakeCSPOutputPSP(DeterministicPSP):
    def simulate(self, args):
        (ids, exp) = args.operandValues()
        # point to the desugared source code location of lambda body
        addr = args.operandNodes[1].address.last.append(1)
        return VentureSPRecord(CompoundSP(ids, exp, addr, args.env))

make_csp = TypedPSP(MakeCSPOutputPSP(), SPType(
    [t.HomogeneousArrayType(t.SymbolType()), t.ExpressionType()],
    t.AnyType("a compound SP")))

class CompoundSP(SimpleRequestingSP):
    def __init__(self, ids, exp, addr, env):
        self.ids = ids
        self.exp = exp
        self.addr = addr
        self.env = env

    def request(self, args, constraint):
        if len(self.ids) != len(args.operandNodes):
            raise Exception("Wrong number of arguments: compound takes exactly %d arguments, got %d." % (len(self.ids), len(args.operandNodes)))
        extendedEnv = VentureEnvironment(self.env, self.ids, args.operandNodes)
        return ESR(args.node, self.exp, self.addr, extendedEnv)

def test():
    from venture.lite.discrete import CBetaBernoulliOutputPSP, BetaBernoulliSPAux
    from venture.lite.continuous import NormalOutputPSP
    from venture.lite.sp_help import deterministic_psp
    from venture.shortcuts import make_lite_church_prime_ripl

    normal = SimpleRandomSPWrapper(NormalOutputPSP())

    args = SimpleArgsWrapper([10, 1])
    print(normal.apply(args, None))
    print(normal.apply(args, None))
    print(normal.apply(args, 11))
    print(normal.apply(args, 12))
    print(normal.apply(args, 13))
    print(normal.apply(args, 9))
    print(normal.apply(args, 8))
    print(normal.apply(args, 7))

    coin = SimpleRandomSPWrapper(CBetaBernoulliOutputPSP(1.0, 1.0))
    bbaux = BetaBernoulliSPAux()
    args = SimpleArgsWrapper([], bbaux)
    print(coin.apply(args, False))
    print(coin.apply(args, False))
    print(coin.apply(args, True))
    print(coin.apply(args, True))
    (x, w) = coin.apply(args, None)
    print((x, w))
    print(coin.unapply(False, args, False))
    print(coin.unapply(False, args, False))
    print(coin.unapply(True, args, True))
    print(coin.unapply(True, args, True))
    print(coin.unapply(x, args, None))

    plus = SimpleDeterministicSPWrapper(deterministic_psp(lambda x, y: x + y))

    print(plus.apply(SimpleArgsWrapper([1, 2]), None))
    print(plus.apply(SimpleArgsWrapper([3, 4]), None))
    print(plus.unapply(3, SimpleArgsWrapper([1, 2]), None))
    print(plus.unapply(7, SimpleArgsWrapper([3, 4]), None))
    try:
        plus.apply([2,2], 5)
    except AssertionError:
        pass
    else:
        assert False

if __name__ == '__main__':
    test()
