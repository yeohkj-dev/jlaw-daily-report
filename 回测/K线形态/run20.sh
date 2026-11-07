#!/usr/bin/env bash
# 20 年版整套回测（数据：回测/cache20，2005 起）。输出文件名都带 20，不会盖掉 5 年版。
set -e
cd "$(dirname "$0")"
export BT_TAG=20 PYTHONIOENCODING=utf-8
# exit_bt 已跑过
python backtest.py     > backtest20.log 2>&1; echo "backtest 1 done"
python bias.py         > bias20.log 2>&1;     echo "bias done"
python stats.py        > stats20.log 2>&1;    echo "stats 1 done"
python backtest.py 2   > backtest2_20.log 2>&1; python stats.py 2 > stats2_20.log 2>&1; echo "set 2 done"
python backtest.py 3   > backtest3_20.log 2>&1; python stats.py 3 > stats3_20.log 2>&1; echo "set 3 done"
python base_up.py      > base_up20.log 2>&1;  echo "base_up done"
python cond_base.py    > cond_base20.log 2>&1; echo "cond_base done"
python crash_study.py  > crash20.log 2>&1;   echo "crash done"
python backtest.py 4   > backtest4_20.log 2>&1; python stats.py 4 > stats4_20.log 2>&1; echo "set 4 done"
