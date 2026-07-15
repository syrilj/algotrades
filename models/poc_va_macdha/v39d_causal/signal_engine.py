"""Causal v39d teacher snapshot used by v48 and baseline audits."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _teacher_class():
    here = Path(__file__).resolve().parent
    for path in (here / "v48_teachers.py", here.parent / "_shared" / "v48_teachers.py"):
        if path.exists():
            spec = importlib.util.spec_from_file_location("v39d_causal_teachers", path)
            module = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            return module.TrendTeacher
    raise FileNotFoundError("v48_teachers.py is not bundled with v39d_causal")


class SignalEngine:
    def __init__(self) -> None:
        self._teacher = _teacher_class()()

    def generate(self, data_map):
        return self._teacher.generate(data_map)
