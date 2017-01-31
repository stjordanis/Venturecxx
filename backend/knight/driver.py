from typing import Tuple
from typing import cast

import venture.lite.value as vv 
from venture.parser.venture_script.parse import VentureScriptParser
from venture.sivm.macro_system import desugar_expression
from venture.sivm.core_sivm import _modify_expression

from venture.knight.types import Trace
from venture.knight.types import stack_dict_to_exp
from venture.knight.regen import regen
from venture.knight.sp import init_env

def top_eval(form):
  # type: (str) -> Tuple[float, vv.VentureValue]
  stack_dict = cast(object, _modify_expression(desugar_expression(VentureScriptParser.instance().parse_expression(form))))
  return regen(stack_dict_to_exp(stack_dict), init_env(), Trace(), Trace())

print top_eval("((x) -> { x })(2)")
print top_eval("normal(2, 1)")
print top_eval("get_current_trace()")
print top_eval("trace_has(get_current_trace())") # False
print top_eval("{ t = get_current_trace(); _ = trace_set(t, 5); trace_get(t) }") # 5
print top_eval("""{
  t1 = get_current_trace();
  t2 = get_current_trace();
  res = regenerate(normal, [0, 1], t1, t2);
  list(res, trace_get(t2)) }""") # (0, List(List(0 . x), x)) where x ~ normal(0, 1)
print top_eval("""{
  t1 = get_current_trace();
  _ = trace_set(t1, 1);
  t2 = get_current_trace();
  res = regenerate(normal, [0, 1], t1, t2);
  list(res, trace_get(t2)) }""") # (0, List(List(-1.41 . 1), 1))
print top_eval("""{
  t1 = get_current_trace();
  t2 = get_current_trace();
  _ = trace_set(t2, 1);
  res = regenerate(normal, [0, 1], t1, t2);
  list(res, trace_get(t2)) }""") # (0, List(List(0 . 1), 1))
