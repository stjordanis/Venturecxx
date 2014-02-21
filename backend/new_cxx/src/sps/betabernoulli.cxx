#include "sps/betabernoulli.h"
#include <gsl/gsl_rng.h>
#include <gsl/gsl_randist.h>
#include "sps/numerical_helpers.h"


VentureValuePtr MakeBetaBernoulliOutputPSP::simulate(shared_ptr<Args> args, gsl_rng * rng) const
{
  assert(args->operandValues.size() == 2); // TODO throw an error once exceptions work
  
  double alpha = args->operandValues[0]->getDouble();
  double beta = args->operandValues[1]->getDouble();
  
  PSP * requestPSP = new NullRequestPSP();
  PSP * outputPSP = new BetaBernoulliOutputPSP(alpha, beta);
  return VentureValuePtr(new VentureSPRecord(new SP(requestPSP,outputPSP),new BetaBernoulliSPAux()));
}

// BetaBernoulliOutputPSP

  VentureValuePtr BetaBernoulliOutputPSP::simulate(shared_ptr<Args> args, gsl_rng * rng) const
  {
    shared_ptr<BetaBernoulliSPAux> aux = dynamic_pointer_cast<BetaBernoulliSPAux>(args->spaux);
    double a = alpha + aux->heads;
    double b = beta + aux->tails;
    double w = a / (a + b);
    return gsl_ran_flat(trace->rng,0.0,1.0) < w;
  }

  double BetaBernoulliOutputPSP::logDensity(VentureValuePtr value,shared_ptr<Args> args) const
  {
    shared_ptr<BetaBernoulliSPAux> aux = dynamic_pointer_cast<BetaBernoulliSPAux>(args->spaux);
    double a = alpha + aux->heads;
    double b = beta + aux->tails;
    double w = a / (a + b);
    if (value->getBool()) { return log(w); }
    else { return log(1-w); }
  }

  void BetaBernoulliOutputPSP::incorporate(VentureValuePtr value,shared_ptr<Args> args) const
  {
    shared_ptr<BetaBernoulliSPAux> aux = dynamic_pointer_cast<BetaBernoulliSPAux>(args->spaux);
    if (value->getBool()) { aux->heads++; }
    else { aux->tails++; }
  }
  void BetaBernoulliOutputPSP::unincorporate(VentureValuePtr value,shared_ptr<Args> args) const
  {
    shared_ptr<BetaBernoulliSPAux> aux = dynamic_pointer_cast<BetaBernoulliSPAux>(args->spaux);
    if (value->getBool()) { aux->heads++; }
    else { aux->tails++; }
  }

double BetaBernoulliOutputPSP::logDensityOfCounts(shared_ptr<SPAux> spAux) const { assert(false); } // TODO

// MakeUncollapsed

VentureValuePtr MakeUBetaBernoulliOutputPSP::simulate(shared_ptr<Args> args, gsl_rng * rng) const
{
  assert(args->operandValues.size() == 2);

  double alpha = args->operandValues[0]->getDouble();
  double beta = args->operandValues[1]->getDouble();

  double p = gsl_ran_beta(rng,alpha,beta);

  UBetaBernoulliSPAux * aux = new UBetaBernoulliAux(p);
  PSP * requestPSP = new NullRequestPSP();
  PSP * outputPSP = new UBetaBernoulliOutputPSP();
  return VentureValuePtr(new VentureSPRecord(new SP(requestPSP,outputPSP),aux));
}

double MakeUBetaBernoulliOutputPSP::logDensity(VentureValuePtr value, shared_ptr<Args> args) const
{
  assert(args->operandValues.size() == 2);

  double alpha = args->operandValues[0]->getDouble();
  double beta = args->operandValues[1]->getDouble();
  
  shared_ptr<VentureSPRecord> spRecord = dynamic_pointer_cast<VentureSPRecord>(value);
  assert(spRecord);
  shared_ptr<UBetaBernoulli> spAux = dynamic_pointer_cast<UBetaBernoulli>(spRecord->spAux);
  assert(spAux);

  return BetaBernoulliLogLikelihood(spAux->p,alpha,beta);
}

// Uncollapsed SP

void UBetaBernoulliSP::AEInfer(shared_ptr<Args> args,gsl_rng * rng) const { assert(false); }

// Uncollapsed PSP

VentureValuePtr UBetaBernoulliOutputPSP::simulate(shared_ptr<Args> args, gsl_rng * rng) const
{
  shared_ptr<UBetaBernoulliSPAux> aux = dynamic_pointer_cast<UBetaBernoulliSPAux>(args->spaux);
  int n = gsl_ran_bernoulli(rng,aux->p);
  if (n == 0) { return VentureValuePtr(new VentureBool(false)); }
  else if (n == 1) { return VentureValuePtr(new VentureBool(true)); }
  else { assert(false); }
}

double UBetaBernoulliOutputPSP::logDensity(VentureValuePtr value,shared_ptr<Args> args) const
{
  shared_ptr<UBetaBernoulliSPAux> aux = dynamic_pointer_cast<UBetaBernoulliSPAux>(args->spaux);
  double p = aux->p;
  if (value->getBool()) { return log(w); }
  else { return log(1-w); }
}

void UBetaBernoulliOutputPSP::incorporate(VentureValuePtr value,shared_ptr<Args> args) const
{
  shared_ptr<UBetaBernoulliSPAux> aux = dynamic_pointer_cast<UBetaBernoulliSPAux>(args->spaux);
  if (value->getBool()) { aux->heads++; }
  else { aux->tails++; }
}

void UBetaBernoulliOutputPSP::unincorporate(VentureValuePtr value,shared_ptr<Args> args) const;
{
  shared_ptr<UBetaBernoulliSPAux> aux = dynamic_pointer_cast<UBetaBernoulliSPAux>(args->spaux);
  if (value->getBool()) { aux->heads++; }
  else { aux->tails++; }
}







#endif
