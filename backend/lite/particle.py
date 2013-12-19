from trace import Trace

class Particle(Trace):
  def __init__(self,trace):
    self.base = trace
    self.cache = {} # TODO persistent map from nodes to node records

  def _at(self,node):
    return self.cache[node]

  def _alterAt(self,node,f):
    self.cache = self.cache.insert(node,f(self._at(node)))

  def valueAt(self,node):
    return self._at(node).value
  def setValueAt(self,node,value):
    self._alterAt(node, lambda r: r.update(value=value))
  def madeSPAt(self,node):
    return self._at(node).madeSP
  def setMadeSPAt(self,node,sp):
    self._alterAt(node, lambda r: r.update(madeSP=sp))
  def madeSPAuxAt(self,node):
    return self._at(node).madeSPAux
  def setMadeSPAuxAt(self,node,aux):
    self._alterAt(node, lambda r: r.update(madeSPAux=aux))
  def esrParentsAt(self,node):
    return self._at(node).esrParents
  def appendEsrParentAt(self,node,parent):
    self._alterAt(node, lambda r: r.append_esrParent(parent))
  def popEsrParentAt(self,node):
    ans = self._at(node).top_esrParent()
    self._alterAt(node, lambda r: r.pop_esrParent())
    return ans
  def childrenAt(self,node):
    return self._at(node).children
  def addChildAt(self,node,child):
    self._alterAt(node, lambda r: r.add_child(child))
  def removeChildAt(self,node,child):
    self._alterAt(node, lambda r: r.remove_child(child))
  def registerFamilyAt(self,node,esrId,esrParent):
    self._alterAt(node, lambda r: r.registerFamily(esrId,esrParent))
  def unregisterFamilyAt(self,node,esrId):
    self._alterAt(node, lambda r: r.unregisterFamily(esrId))
  def numRequestsAt(self,node):
    return self._at(node).numRequests
  def incRequestsAt(self,node):
    self._alterAt(node, lambda r: r.update(numRequests = r.numRequests + 1))
  def decRequestsAt(self,node):
    self._alterAt(node, lambda r: r.update(numRequests = r.numRequests - 1))

class Record(object):
  def __init__(self,value=None,madeSP=None,madeSPAux=None,esrParents=None,children=None,numRequests=0):
    self.value = value
    self.madeSP = madeSP
    self.madeSPAux = madeSPAux
    self.esrParents = if esrParents: esrParents else: []
    self.children = if children: children else: []
    self.numRequests = numRequests

  def _copy():
    return Record(self.value, self.madeSP, self.madeSPAux, self.esrParents, self.children, self.numRequests)

  def update(self,value=None,madeSP=None,madeSPAux=None,esrParents=None,children=None,numRequests=None):
    ans = self._copy()
    if value: ans.value = value
    if madeSP: ans.madeSP = madeSP
    if madeSPAux: ans.madeSPAux = madeSPAux
    if esrParents: ans.esrParents = esrParents
    if children: ans.children = children
    if numRequests: ans.numRequests = numRequests
    return ans

  def add_child(self,child):
    new_children = [c for c in self.children]
    new_children.add(child)
    return self.update(children=new_children)

  def remove_child(self,child):
    new_children = [c for c in self.children]
    new_children.remove(child)
    return self.update(children=new_children)

  def top_espParent(self):
    return self.esrParents[len(self.esrParents)-1]

  def pop_esrParent(self):
    new_esrParents = [p for p in self.esrParents]
    new_esrParents.pop()
    return self.update(esrParents=new_esrParents)

  def append_esrParent(self,parent):
    new_esrParents = [p for p in self.esrParents]
    new_esrParents.append(parent)
    return self.update(esrParents=new_esrParents)
