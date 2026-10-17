"""
启动从站：
  python run_slave.py                      # 默认从数据库读
  python run_slave.py --mode coverage      # 强制覆盖模式（22 秒覆盖全部测点）
  python run_slave.py --mode random        # 强制随机模式
  python run_slave.py --source db          # 明确指定数据库
  python run_slave.py --source generator   # 用生成器（无数据库时）
  python run_slave.py --source generator --mode coverage
  python run_slave.py --port 5020
  python run_slave.py --seed 42            # 固定随机种子
"""
import argparse
from slave.server import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["db", "generator"], default="db")
    parser.add_argument("--mode", choices=["coverage", "random"], default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=502)
    args = parser.parse_args()
    main(source_kind=args.source, mode=args.mode, seed=args.seed,
         host=args.host, port=args.port)