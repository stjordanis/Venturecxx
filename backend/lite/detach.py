def unconstrain(node):
  if node.isLookupNode(): return unconstrain(node.sourceNode())
  if isinstance(node.psp(),ESRReferencePSP): return unconstrain(node.esrParents[0])

  if node.psp().isRandom(): trace.registerRandomChoice(node)
  node.psp().unincorporate(node.value,node.args())
  weight = node.psp().logDensity(value,node.args())
  node.psp().incorporateOutput(node.value,node.args())
  return weight

def detachAndExtract(trace,border,scaffold):
  weight = 0
  omegaDB = OmegaDB()
  for node in reversed(border):
    if scaffold.isAbsorbing(node):
      weight += detach(trace,scaffold,shouldRestore,omegaDB)
    else:
      if node.isConstrained: weight += unconstrain(node)
      weight += extract(trace,scaffold,shouldRestore,omegaDB)
  return weight
  
def extractParents(trace,node,scaffold,omegaDB):
  weight = 0
  for parent in reversed(node.parents()): weight += extract(trace,node,scaffold,omegaDB)
  return weight

def detach(trace,node,scaffold,omegaDB):
  # we need to pass groundValue here in case the return value is an SP
  # in which case the node would only contain an SPRef
  node.psp().unincorporate(node.groundValue(),node.args())
  weight = node.psp().logDensity(node.groundValue(),node.args())
  weight += extractParents(trace,node,scaffold,omegaDB)
  return weight

def extract(trace,node,scaffold,omegaDB):
  weight = 0
  if isinstance(node.value,SPRef) and node.value.makerNode != node and scaffold.isAAA(node.value.makerNode):
    weight += extract(trace,node.value.makerNode,scaffold,omegaDB)

  if scaffold.isResampling(node):
    scaffold.decrementRegenCount(node)
    if scaffold.regenCount(node) == 0:
      if node.isApplicationNode(): 
        if node.isRequestNode(): weight += unevalRequests(trace,node,scaffold,omegaDB)
        weight += unapplyPSP(node,scaffold,omegaDB)
      weight += extractParents(node,scaffold,omegaDB)

  return weight
