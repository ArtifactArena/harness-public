"""Compile unchanged Python bookkeeping bodies; retain their NumPy calls."""
import ast,hashlib,textwrap
from pathlib import Path
here=Path(__file__).parent
root=here.parents[2]
episode=root/'mjarena/runner/episode.py'

def method(path,classname,name,newname):
    text=path.read_text();tree=ast.parse(text)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==classname)
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
    body=textwrap.dedent('\n'.join(text.splitlines()[node.lineno-1:node.end_lineno]))
    return body.replace('def '+name+'(', 'def '+newname+'(',1)

header='''# cython: language_level=3, annotation_typing=False, infer_types=False
import numpy as np
from mjarena.agents.types import BotObservation
from mjarena.envs.occupancy_grid import build_arena_grid, build_arena_mass_grid
'''
code=header+'\n'+method(episode,'Match','build_bot_observation','build_bot_observation')+'\n\n'
code+='SOURCE_HASHES='+repr({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [episode]})+'\n'
(here/'_glue.pyx').write_text(code)
