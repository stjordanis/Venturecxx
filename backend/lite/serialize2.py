from venture.lite.engine import Engine
from venture.lite.omegadb import OmegaDB
from venture.lite.scaffold import constructScaffold
from venture.lite.detach import detachAndExtract
from venture.lite.regen import regenAndAttach
from venture.lite.consistency import assertTrace, assertTorus

class StackDB(OmegaDB):
    def __init__(self):
        super(StackDB, self).__init__()
        self.values = []
        self.spFamilyDBs = []
    def hasValueFor(self, node):
        return True
    def getValue(self, node):
        return self.values.pop()
    def extractValue(self, node, value):
        self.values.append(value)
    def getESRParent(self, sp, id):
        return self.spFamilyDBs.pop()
    def registerSPFamily(self, sp, id, esrParent):
        self.spFamilyDBs.append(esrParent)

def ser_deser(engine):
    trace = engine.getDistinguishedTrace()
    scaffold = constructScaffold(trace, [trace.getAllNodesInScope('default')])
    assertTrace(trace, scaffold)

    _, omegaDB = detachAndExtract(trace, scaffold.border[0], scaffold, omegaDB = StackDB())
    assertTorus(scaffold)

    _ = regenAndAttach(trace, scaffold.border[0], scaffold, True, omegaDB, {})
    assertTrace(trace, scaffold)

    return engine

def ser_deser(engine):
    old_trace = engine.getDistinguishedTrace()
    directives = engine.directives
    directiveCounter = engine.directiveCounter

    engine = Engine()
    engine.directives = directives
    for did, directive in sorted(directives.items()):
        engine.directiveCounter = did - 1
        engine.replay(directive)
    engine.directiveCounter = directiveCounter
    new_trace = engine.getDistinguishedTrace()

    old_scaffold = constructScaffold(old_trace, [old_trace.getAllNodesInScope('default')])
    new_scaffold = constructScaffold(new_trace, [new_trace.getAllNodesInScope('default')])

    _, oldDB = detachAndExtract(old_trace, old_scaffold.border[0], old_scaffold, omegaDB = StackDB())
    _, newDB = detachAndExtract(new_trace, new_scaffold.border[0], new_scaffold)

    # _ = regenAndAttach(old_trace, old_scaffold.border[0], old_scaffold, True, oldDB, {})
    # _ = regenAndAttach(new_trace, new_scaffold.border[0], new_scaffold, True, newDB, {})
    _ = regenAndAttach(new_trace, new_scaffold.border[0], new_scaffold, True, oldDB, {})

    return engine

def test_omegadb_serialize():
    from venture.shortcuts import make_lite_church_prime_ripl
    v = make_lite_church_prime_ripl()
    v.assume('tricky_prob', '(beta 1.0 1.0)')
    v.assume('coin_weight', '(mem (lambda (x) (if (flip tricky_prob) (beta 1.0 1.0) 0.5)))')
    v.assume('flip_coin', '(lambda (x) (flip (coin_weight x)))')
    # v.assume('coin', '(mem (lambda (x) (if (flip tricky_prob) (make_beta_bernoulli 1.0 1.0) flip)))')
    # v.assume('flip_coin', '(lambda (x) ((coin x)))')
    for i in range(5):
        v.observe('(flip_coin {})'.format(i), 'true')
    for i in range(10):
        v.predict('(flip_coin {})'.format(i), label='x{}'.format(i))
    v.infer(0)
    for i in range(10):
        print v.report('x{}'.format(i))
    v.sivm.core_sivm.engine = ser_deser(v.sivm.core_sivm.engine)
    for i in range(10):
        print v.report('x{}'.format(i))

if __name__ == '__main__':
    test_omegadb_serialize()
