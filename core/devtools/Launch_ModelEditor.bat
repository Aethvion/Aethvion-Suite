@echo off
echo Starting Aethvion Model Defaults Editor...
echo Opening browser to http://localhost:8001
start http://localhost:8001
cd ..\..
python -m core.devtools.model_editor.server
pause
