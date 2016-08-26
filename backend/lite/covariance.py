# -*- coding: utf-8 -*-

# Copyright (c) 2016 MIT Probabilistic Computing Project.
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

import numpy as np
import scipy.spatial.distance

# Trivial covariance kernel

def const(c):
  """Constant kernel, everywhere equal to c."""
  def k(x_1, x_2):
    return c*np.ones((len(x_1), len(x_2)))
  return k

def d_const(c):
  def k(_x_1, _x_2):
    return [c]
  return k

# Isotropic covariance kernels

def isotropic(f):
  """Isotropic kernel: k(x_1, x_2) = f(||x_1 - x_2||^2)."""
  def k(x_1, x_2):
    x_1 = x_1.reshape(len(x_1), -1)
    x_2 = x_2.reshape(len(x_2), -1)
    return f(scipy.spatial.distance.cdist(x_1, x_2, 'sqeuclidean'))
  return k

def delta(tolerance):
  """Delta kernel: 1, if r^2 is at most tolerance; else 0."""
  def f(r2):
    return 1.*(r2 <= tolerance)
  return isotropic(f)

def bump(tolerance, steepness):
  """Bump kernel: e^{-t/r^s}"""
  def f(r2):
    t = tolerance
    s = steepness
    return np.exp(-t/(r2**(s/2.)))
  return isotropic(f)

def d_bump(tolerance, steepness):
  def df(r2):
    # d/dt e^{-t/r^s} = -e^{-t/r^s}/r^s
    # d/ds e^{-t/r^s} = e^{-t/r^s} (-t) d/ds r^{-s}
    #   = e^{-t/r^s} (-t) (-log r) r^{-s}
    #   = e^{-t/r^s} t r^{-s} log r
    t = tolerance
    s = steepness
    r_s = r2**(-s/2.)
    k = np.exp(-t*r_s)
    return [-k*r_s, k*t*r_s*np.log(r2)/2.]
  return isotropic(df)

def _se(r2, l2):
  return np.exp(-0.5 * r2 / l2)

def se(l2):
  """Squared-exponential kernel: e^(-r^2 / (2 l^2))"""
  return isotropic(lambda r2: _se(r2, l2))

def _d_se_l2(r2, l2):
  """d/d(l^2) of squared exponential kernel."""
  return _se(r2, l2) * -0.5 * r2 / (l2*l2)

def d_se(l2):
  return isotropic(lambda r2: [_d_se_l2(r2, l2)])

def periodic(l2, T):
  """Periodic kernel: e^(-(2 sin(2pi r / T))^2 / (2 l^2))"""
  sin = np.sin
  pi = np.pi
  sqrt = np.sqrt
  def f(r2):
    d = 2.*sin(2.*pi*sqrt(r2)/T)
    return _se(d**2, l2)
  return isotropic(f)

def d_periodic(l2, T):
  cos = np.cos
  pi = np.pi
  sin = np.sin
  sqrt = np.sqrt
  def df(r2):
    t = 2.*pi*sqrt(r2)/T
    d2 = (2.*sin(t))**2
    return [_d_se_l2(d2, l2), _se(d2, l2) * (4/(l2*T)) * t * sin(t) * cos(t)]
  return isotropic(df)

def rq(l2, alpha):
  """Rational quadratic kernel: (1 + r^2/(2 alpha l^2))^-alpha"""
  def f(r2):
    return np.power(1. + r2/(2 * alpha * l2), -alpha)
  return isotropic(f)

def matern(l2, df):
  """Matérn kernel with squared length-scale l2 and nu = df/2."""
  import scipy.special
  nu = df/2.
  c = np.exp((1. - nu)*np.log(2.) - scipy.special.gammaln(nu))
  def f(r2):
    q = np.sqrt(df*r2/l2)
    return c * np.power(q, nu) * scipy.special.kv(nu, q)
  return isotropic(f)

def matern_32(l2):
  """Matérn kernel specialized with three degrees of freedom."""
  def f(r2):
    q = np.sqrt(3.*r2/l2)
    return (1. + q)*np.exp(-q)
  return isotropic(f)

def matern_52(l2):
  """Matérn kernel specialized with five degrees of freedom."""
  def f(r2):
    q2 = 5.*r2/l2
    q = np.sqrt(q2)
    return (1. + q + q2/3.)*np.exp(-q)
  return isotropic(f)

def linear(x):
  """Linear covariance kernel: k(x_1, x_2) = (x_1 - x) (x_2 - x)."""
  def k(x_1, x_2):
    return np.outer(x_1 - x, x_2 - x)
  return k

def d_linear(x):
  def dk(x_1, x_2):
    return [np.ones(x.shape)]
  return dk

# Composite covariance kernels

def bias(s2, k):
  """Kernel k biased by the constant squared bias s^2.

  Every covariance, including variance/self-covariance, has s^2 added.
  """
  return lambda x_1, x_2: s2 + k(x_1, x_2)

def d_bias(s2, k):
  def dk(x_1, x_2):
    return [1] + k.df(x_1, x_2)
  return dk

def scale(s2, k):
  """Kernel k scaled by squared output factor s^2."""
  return lambda x_1, x_2: s2 * k(x_1, x_2)

def d_scale(s2, k):
  def dk(x_1, x_2):
    return [k(x_1, x_2)] + [s2*dk_i for dk_i in k.df(x_1, x_2)]
  return dk

def sum(k_a, k_b):
  """Sum of kernels k_a and k_b."""
  return lambda x_1, x_2: k_a(x_1, x_2) + k_b(x_1, x_2)

def d_sum(k_a, k_b):
  return lambda x_1, x_2: k_a.df(x_1, x_2) + k_b.df(x_1, x_2)

def product(k_a, k_b):
  """Product of kernels k_a and k_b."""
  return lambda x_1, x_2: k_a(x_1, x_2) * k_b(x_1, x_2)

def d_product(k_a, k_b):
  def dk(x_1, x_2):
    ka = k_a(x_1, x_2)
    kb = k_b(x_1, x_2)
    dk_a = [dk_ai*kb for dk_ai in k_a.df(x_1, x_2)]
    dk_b = [ka*dk_bi for dk_bi in k_b.df(x_1, x_2)]
    return dk_a + dk_b
  return dk
