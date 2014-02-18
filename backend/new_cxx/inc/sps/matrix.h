#ifndef SPS_MATRIX_H
#define SPS_MATRIX_H

#include "psp.h"
#include "args.h"

struct MatrixOutputPSP : PSP
{
  VentureValuePtr simulate(shared_ptr<Args> args, gsl_rng * rng) const;
};


#endif
