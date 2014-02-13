from builtin import builtInValues, builtInSPs
from env import VentureEnvironment
from node import ConstantNode,LookupNode,RequestNode,OutputNode,Args
import math
from regen import constrain,processMadeSP, evalFamily
from detach import unconstrain, unevalFamily
from value import SPRef, ExpressionType, VentureValue
from scaffold import Scaffold
from infer import mixMH,MHOperator,MeanfieldOperator,BlockScaffoldIndexer,EnumerativeGibbsOperator,PGibbsOperator,ParticlePGibbsOperator
from omegadb import OmegaDB
from smap import SMap
from sp import SPFamilies
from nose.tools import assert_equal,assert_is_not_none
from scope import ScopeIncludeOutputPSP
from regen import regenAndAttach
from detach import detachAndExtract
from scaffold import constructScaffold
from consistency import assertTorus
from lkernel import DeterministicLKernel
from psp import ESRRefOutputPSP
import pdb

class Trace(object):
  def __init__(self):

    self.globalEnv = VentureEnvironment()
    for name,val in builtInValues().iteritems():
      self.globalEnv.addBinding(name,ConstantNode(val))
    for name,sp in builtInSPs().iteritems():
      spNode = self.createConstantNode(sp)
      processMadeSP(self,spNode,False)
      assert isinstance(self.valueAt(spNode), SPRef)
      self.globalEnv.addBinding(name,spNode)
    self.globalEnv = VentureEnvironment(self.globalEnv) # New frame so users can shadow globals

    self.rcs = set()
    self.ccs = set()
    self.aes = set()
    self.unpropagatedObservations = {} # {node:val}
    self.families = {}
    self.scopes = {} # :: {scope-name:smap{block-id:set(node)}}

  def registerAEKernel(self,node): self.aes.add(node)
  def unregisterAEKernel(self,node): self.aes.remove(node)

  def registerRandomChoice(self,node):
    assert not node in self.rcs
    self.rcs.add(node)
    self.registerRandomChoiceInScope("default",node,node)

  def registerRandomChoiceInScope(self,scope,block,node):
    assert block is not None
    if not scope in self.scopes: self.scopes[scope] = SMap()
    if not block in self.scopes[scope]: self.scopes[scope][block] = set()
    assert not node in self.scopes[scope][block]
    self.scopes[scope][block].add(node)
    assert not scope == "default" or len(self.scopes[scope][block]) == 1

  def unregisterRandomChoice(self,node): 
    assert node in self.rcs
    self.rcs.remove(node)
    self.unregisterRandomChoiceInScope("default",node,node)

  def unregisterRandomChoiceInScope(self,scope,block,node):
    self.scopes[scope][block].remove(node)
    assert not scope == "default" or len(self.scopes[scope][block]) == 0
    if len(self.scopes[scope][block]) == 0: del self.scopes[scope][block]
    if len(self.scopes[scope]) == 0: del self.scopes[scope]

  def registerConstrainedChoice(self,node):
    self.ccs.add(node)
    self.unregisterRandomChoice(node)

  def unregisterConstrainedChoice(self,node):
    assert node in self.ccs
    self.ccs.remove(node)
    if self.pspAt(node).isRandom(): self.registerRandomChoice(node)

  def createConstantNode(self,val): return ConstantNode(val)
  def createLookupNode(self,sourceNode): 
    lookupNode = LookupNode(sourceNode)
    self.setValueAt(lookupNode,self.valueAt(sourceNode))
    self.addChildAt(sourceNode,lookupNode)
    return lookupNode

  def createApplicationNodes(self,operatorNode,operandNodes,env):
    requestNode = RequestNode(operatorNode,operandNodes,env)
    outputNode = OutputNode(operatorNode,operandNodes,requestNode,env)
    self.addChildAt(operatorNode,requestNode)
    self.addChildAt(operatorNode,outputNode)
    for operandNode in operandNodes:
      self.addChildAt(operandNode,requestNode)
      self.addChildAt(operandNode,outputNode)
    requestNode.registerOutputNode(outputNode)
    return (requestNode,outputNode)

  def addESREdge(self,esrParent,outputNode):
    self.incRequestsAt(esrParent)
    self.addChildAt(esrParent,outputNode)
    self.appendEsrParentAt(outputNode,esrParent)

  def popLastESRParent(self,outputNode):
    assert self.esrParentsAt(outputNode)
    esrParent = self.popEsrParentAt(outputNode)
    self.removeChildAt(esrParent,outputNode)
    self.decRequestsAt(esrParent)
    return esrParent
  
  def disconnectLookup(self,lookupNode):
    self.removeChildAt(lookupNode.sourceNode,lookupNode)

  def reconnectLookup(self,lookupNode):
    self.addChildAt(lookupNode.sourceNode,lookupNode)

  def groundValueAt(self,node):
    value = self.valueAt(node)
    if isinstance(value,SPRef): return self.madeSPAt(value.makerNode)
    else: return value
      
  def argsAt(self,node): return Args(self,node)

  def spRefAt(self,node):
    candidate = self.valueAt(node.operatorNode)
    if not isinstance(candidate, SPRef):
      print "spRef not an spRef"
      print "is a: " + str(type(candidate))
      print node,node.operatorNode
    assert isinstance(candidate, SPRef)
    return candidate
  
  def spAt(self,node): return self.madeSPAt(self.spRefAt(node).makerNode)
  def spFamiliesAt(self,node): 
    spFamilies = self.madeSPFamiliesAt(self.spRefAt(node).makerNode)
    assert isinstance(spFamilies,SPFamilies)
    return spFamilies
  def spauxAt(self,node): return self.madeSPAuxAt(self.spRefAt(node).makerNode)
  def pspAt(self,node):
    if isinstance(node, RequestNode):
      return self.spAt(node).requestPSP
    else:
      assert isinstance(node, OutputNode)
      return self.spAt(node).outputPSP

  #### Stuff that a particle trace would need to override for persistence

  def valueAt(self,node):
    assert node.isAppropriateValue(node.value)
    return node.value

  def setValueAt(self,node,value):
    assert node.isAppropriateValue(value)
    node.value = value

  def madeSPAt(self,node): return node.madeSP
  def setMadeSPAt(self,node,sp): node.madeSP = sp
    
  def madeSPFamiliesAt(self,node):
    assert_is_not_none(node.madeSPFamilies)
    return node.madeSPFamilies

  def setMadeSPFamiliesAt(self,node,families): node.madeSPFamilies = families

  def madeSPAuxAt(self,node): return node.madeSPAux
  def setMadeSPAuxAt(self,node,aux): node.madeSPAux = aux

  def parentsAt(self,node): return node.parents()    
  def definiteParentsAt(self,node): return node.definiteParents()
            
  def esrParentsAt(self,node): return node.esrParents
  def setEsrParentsAt(self,node,parents): node.esrParents = parents
  def appendEsrParentAt(self,node,parent): node.esrParents.append(parent)
  def popEsrParentAt(self,node): return node.esrParents.pop()
    
  def childrenAt(self,node): return node.children
  def setChildrenAt(self,node,children): node.children = children
  def addChildAt(self,node,child): node.children.add(child)
  def removeChildAt(self,node,child): node.children.remove(child)
    
  def registerFamilyAt(self,node,esrId,esrParent): self.spFamiliesAt(node).registerFamily(esrId,esrParent)
  def unregisterFamilyAt(self,node,esrId): self.spFamiliesAt(node).unregisterFamily(esrId)
  def containsSPFamilyAt(self,node,esrId): return self.spFamiliesAt(node).containsFamily(esrId)
  def spFamilyAt(self,node,esrId): return self.spFamiliesAt(node).getFamily(esrId)
  def madeSPFamilyAt(self,node,esrId): return self.madeSPFamiliesAt(node).getFamily(esrId)

  def initMadeSPFamiliesAt(self,node): self.setMadeSPFamiliesAt(node,SPFamilies())
  def clearMadeSPFamiliesAt(self,node): self.setMadeSPFamiliesAt(node,None)

  def numRequestsAt(self,node): return node.numRequests
  def setNumRequestsAt(self,node,num): node.numRequests = num
  def incRequestsAt(self,node): node.numRequests += 1
  def decRequestsAt(self,node): node.numRequests -= 1

  def regenCountAt(self,scaffold,node): return scaffold.regenCounts[node]
  def incRegenCountAt(self,scaffold,node): scaffold.regenCounts[node] += 1
  def decRegenCountAt(self,scaffold,node): scaffold.regenCounts[node] -= 1 # need not be overriden
    
  def isConstrainedAt(self,node): return node in self.ccs
  
  #### For kernels
  def sampleBlock(self,scope): return self.scopes[scope].sample()[0]
  def logDensityOfBlock(self,scope): return -1 * math.log(self.numBlocksInScope(scope))
  def blocksInScope(self,scope): return self.scopes[scope].keys()
  def numBlocksInScope(self,scope): 
    if scope in self.scopes: return len(self.scopes[scope].keys())
    else: return 0

  def getAllNodesInScope(self,scope):
    return set.union(*[self.getNodesInBlock(scope,block) for block in self.scopes[scope].keys()])
    
  def getOrderedSetsInScope(self,scope):
    return [self.getNodesInBlock(scope,block) for block in sorted(self.scopes[scope].keys())]

  def getNodesInBlock(self,scope,block):
    nodes = self.scopes[scope][block]
    if scope == "default": return nodes
    else:
      pnodes = set()
      for node in nodes: self.addRandomChoicesInBlock(scope,block,pnodes,node)
      return pnodes

  def addRandomChoicesInBlock(self,scope,block,pnodes,node):
    if not isinstance(node,OutputNode): return

    if self.pspAt(node).isRandom(): pnodes.add(node)    

    requestNode = node.requestNode
    if self.pspAt(requestNode).isRandom(): pnodes.add(requestNode)

    for esr in self.valueAt(node.requestNode).esrs:
      self.addRandomChoicesInBlock(scope,block,pnodes,self.spFamilyAt(requestNode,esr.id))

    self.addRandomChoicesInBlock(scope,block,pnodes,node.operatorNode)
          
    for i,operandNode in enumerate(node.operandNodes):
      if i == 2 and isinstance(self.pspAt(node),ScopeIncludeOutputPSP):
        (new_scope,new_block,_) = [self.valueAt(randNode) for randNode in node.operandNodes]
        if scope != new_scope or block == new_block: self.addRandomChoicesInBlock(scope,block,pnodes,operandNode)
      else:
        self.addRandomChoicesInBlock(scope,block,pnodes,operandNode)


  def scopeHasEntropy(self,scope): 
    # right now scope in self.scopes iff it has entropy
    return scope in self.scopes and self.numBlocksInScope(scope) > 0

  #### External interface to engine.py
  def eval(self,id,exp):
    assert not id in self.families
    (_,self.families[id]) = evalFamily(self,self.unboxExpression(exp),self.globalEnv,Scaffold(),OmegaDB(),{})
    
  def bindInGlobalEnv(self,sym,id): self.globalEnv.addBinding(sym,self.families[id])

  def extractValue(self,id): return self.boxValue(self.valueAt(self.families[id]))

  def observe(self,id,val):
    node = self.families[id]
    self.unpropagatedObservations[node] = self.unboxValue(val)

  def makeConsistent(self):
    for node,val in self.unpropagatedObservations.iteritems():
      appNode = self.getOutermostNonReferenceApplication(node)
#      print "PROPAGATE",node,appNode
      scaffold = constructScaffold(self,[set([appNode])])
      detachAndExtract(self,scaffold.border[0],scaffold)
      assertTorus(scaffold)
      scaffold.lkernels[appNode] = DeterministicLKernel(self.pspAt(appNode),val)
      xiWeight = regenAndAttach(self,scaffold.border[0],scaffold,False,OmegaDB(),{})
      if xiWeight == float("-inf"): raise Exception("Unable to propagate constraint")
      node.observe(val)
      constrain(self,appNode,node.observedValue)
    self.unpropagatedObservations.clear()

  def getOutermostNonReferenceApplication(self,node):
    if isinstance(node,LookupNode): return self.getOutermostNonReferenceApplication(node.sourceNode)
    assert isinstance(node,OutputNode)      
    if isinstance(self.pspAt(node),ESRRefOutputPSP): return self.getOutermostNonReferenceApplication(self.esrParentsAt(node)[0])
    else: return node
          
  def unobserve(self,id):
    node = self.families[id]
    appNode = self.getOutermostNonReferenceApplication(node)    
    if node.isObservation: unconstrain(self,appNode)
    else:
      assert node in self.unpropagatedObservations
      del self.unpropagatedObservations[node]

  def uneval(self,id):
    assert id in self.families
    unevalFamily(self,self.families[id],Scaffold(),OmegaDB())
    del self.families[id]

  def numRandomChoices(self):
    return len(self.rcs)

  def continuous_inference_status(self): return {"running" : False}

  # params is a hash with keys "kernel", "scope", "block",
  # "transitions" (the latter should be named "repeats").  Right now,
  # "kernel" must be one of "mh" or "meanfield", and "transitions"
  # must be an integer.
  def infer(self,params):
    self.makeConsistent()
    if not self.scopeHasEntropy(params["scope"]):
      return
    for _ in range(params["transitions"]):
      if params["kernel"] == "mh":
        assert params["with_mutation"]
        mixMH(self,BlockScaffoldIndexer(params["scope"],params["block"]),MHOperator())
      elif params["kernel"] == "meanfield":
        assert params["with_mutation"]        
        mixMH(self,BlockScaffoldIndexer(params["scope"],params["block"]),MeanfieldOperator(10,0.0001))
      elif params["kernel"] == "gibbs":
        assert params["with_mutation"]        
        mixMH(self,BlockScaffoldIndexer(params["scope"],params["block"]),EnumerativeGibbsOperator())
      elif params["kernel"] == "pgibbs":
        if params["with_mutation"]:
          mixMH(self,BlockScaffoldIndexer(params["scope"],params["block"]),PGibbsOperator(int(params["particles"])))
        else:
          mixMH(self,BlockScaffoldIndexer(params["scope"],params["block"]),ParticlePGibbsOperator(int(params["particles"])))          
      else: raise Exception("INFER (%s) MH is implemented" % params["kernel"])

      for node in self.aes: self.madeSPAt(node).AEInfer(self.madeSPAuxAt(node))

  def get_seed(self):
    # TODO Trace does not support seed control because it uses
    # Python's native randomness.
    return 0

  def getGlobalLogScore(self):
    # TODO Get the constrained nodes too
    return sum([self.pspAt(node).logDensity(self.groundValueAt(node),self.argsAt(node)) for node in self.rcs.union(self.ccs)])

  #### Helpers (shouldn't be class methods)

  # TODO temporary, probably need an extra layer of boxing for VentureValues
  # as in CXX
  def boxValue(self,val): return val.asStackDict()
  def unboxValue(self,val): return VentureValue.fromStackDict(val)
  def unboxExpression(self,exp):
    return ExpressionType().asPython(VentureValue.fromStackDict(exp))

#################### Misc for particle commit

  def addNewMadeSPFamilies(self,node,newMadeSPFamilies):
    if node.madeSPFamilies is None: node.madeSPFamilies = SPFamilies()
    for id,root in newMadeSPFamilies.iteritems():
      node.madeSPFamilies.registerFamily(id,root)

  def addNewChildren(self,node,newChildren): 
    for child in newChildren:
      node.children.add(child)
