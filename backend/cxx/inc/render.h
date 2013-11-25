#ifndef RENDER_H
#define RENDER_H

#include <string>
#include <cstdint>
#include <map>
#include <set>

struct Trace;
struct Node;
struct Scaffold;

using namespace std;

enum class EdgeType { OP, ARG, LOOKUP, ESR, REQUEST };

struct Edge
{
  Edge(Node * start, Node * end, EdgeType edgeType):
    start(start), end(end), edgeType(edgeType) {}

  Node * start;
  Node * end;
  EdgeType edgeType;
};

struct Renderer
{
  Renderer();
  void dotTrace(Trace * trace, Scaffold * scaffold);

  void reset();
  string getNextClusterIndex();
  
  void dotHeader();
  void dotFooter();

  void dotStatements();
  void dotNodes();
  void dotEdges();
  void dotVentureFamilies();
  void dotSPFamilies();

  void dotNodesInFamily(Node * root);

// Subgraphs
  void dotSubgraphStart(string name,string label);
  void dotSubgraphEnd();

// Nodes
  void dotNode(Node * node);
  map<string,string> getNodeAttributes(Node * node);
  void dotAttributes(const map<string,string> & attributes);

  string getNodeShape(Node * node);
  string getNodeFillColor(Node * node);
  string getNodeStyle(Node * node);
  string getNodeLabel(Node * node);

// Edges
  void dotFamilyIncomingEdges(Node * node);
  void dotEdge(Edge e);
  map<string,string> getEdgeAttributes(Edge e);
  string getEdgeArrowhead(Edge e);
  string getEdgeStyle(Edge e);
  string getEdgeColor(Edge e);

  Trace * trace;
  Scaffold * scaffold;
  string dot{""};
  uint32_t numClusters{0};

};

#endif
