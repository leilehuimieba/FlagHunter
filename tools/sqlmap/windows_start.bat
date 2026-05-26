chcp 65001

@echo off

@echo.
@echo *********************sqlmap*********************
@echo 使用:  ..\Python38\python.exe sqlmap.py [参数]
@echo "******************************************************
@echo.
@echo.
@echo.

%~d0    %进入这个脚本执行的盘符%
cd %~dp0   %进入这个脚本执行的目录%

..\Python38\python.exe sqlmap.py








cmd
