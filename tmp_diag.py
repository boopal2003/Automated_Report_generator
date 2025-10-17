# tmp_diag.py — diagnostic for vendored packages
import os, sys, importlib, pkgutil, traceback

pkg_path = os.path.join(os.getcwd(), "packages")
# prefer vendored packages first
sys.path.insert(0, pkg_path)
sys.path.insert(0, os.getcwd())

print("--- sys.path (first 5) ---")
for p in sys.path[:5]:
    print(p)

print("\n--- listing modules found in packages (first 200) ---")
try:
    found = [m.name for m in pkgutil.iter_modules(path=[pkg_path])]
    print(found[:200])
except Exception:
    traceback.print_exc()

print("\n--- trying import openai ---")
try:
    m = importlib.import_module("openai")
    print("openai OK ->", getattr(m, "__file__", None))
except Exception:
    traceback.print_exc()

print("\n--- trying import pyodbc ---")
try:
    m2 = importlib.import_module("pyodbc")
    print("pyodbc OK ->", getattr(m2, "__file__", None))
except Exception:
    traceback.print_exc()
