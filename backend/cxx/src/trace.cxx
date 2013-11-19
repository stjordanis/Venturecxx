#include <iostream>
#include <cassert>
#include <cstdlib>
#include <ctime>

#include "node.h"
#include "trace.h"
#include "builtin.h"
#include "sp.h"

#include "flush.h"
#include "value.h"
#include "utils.h"
#include "env.h"

#include <boost/range/adaptor/reversed.hpp>

using boost::adaptors::reverse;

Trace::Trace()
{
  gsl_rng_set (rng,time(NULL));
  
  primitivesEnv = new VentureEnvironment;
  for (pair<string,VentureValue *> p : initBuiltInValues()) 
  { primitivesEnv->addBinding(new VentureSymbol(p.first),new Node(NodeType::VALUE,p.second)); }

  for (pair<string,SP *> p : initBuiltInSPs())
  { 
    Node * spNode = new Node(NodeType::VALUE);
    spNode->setValue(new VentureSP(p.second));
    processMadeSP(spNode);
    primitivesEnv->addBinding(new VentureSymbol(p.first),spNode);
  }

  globalEnv = new VentureEnvironment(primitivesEnv);

}

Trace::~Trace()
{

  // OmegaDB * omegaDB = new OmegaDB;
  // for (map<size_t, pair<Node *,VentureValue*> >::reverse_iterator iter = ventureFamilies.rbegin(); 
  //      iter != ventureFamilies.rend();
  //      ++iter)
  // { 
  //   Node * root = iter->second.first;
  //   if (root->isObservation()) 
  //   { 
  //     unconstrain(root,true); 
  //   }
  //   detachVentureFamily(root,omegaDB); 
  //   destroyExpression(iter->second.second);
  //   destroyFamilyNodes(root);
  // }

  // flushDB(omegaDB,false);

  // globalEnv->destroySymbols();
  // delete globalEnv;

  // for (pair<string,Node*> p : primitivesEnv->frame)
  // {
  //   Node * node = p.second;

  //   if (dynamic_cast<VentureSP*>(node->getValue()))
  //   { teardownMadeSP(node,false,omegaDB); }

  //   delete node->getValue();
  //   delete node;
  // }
  // primitivesEnv->destroySymbols();
  // delete primitivesEnv;

  // for (pair< pair<string,bool >, uint32_t> pp : callCounts)
  // {
  //   assert(callCounts[make_pair(pp.first.first,false)] == callCounts[make_pair(pp.first.first,true)]);
  // }



  // gsl_rng_free(rng);

}

void Trace::addApplicationEdges(Node * operatorNode,const vector<Node *> & operandNodes,Node * requestNode, Node * outputNode)
{
  Node::addOperatorEdge(operatorNode,requestNode);
  Node::addOperatorEdge(operatorNode,outputNode);

  Node::addOperandEdges(operandNodes, requestNode);
  Node::addOperandEdges(operandNodes, outputNode);

  Node::addRequestEdge(requestNode, outputNode);
}
