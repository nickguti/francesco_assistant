import sys
import logging
from src.commands import parse_local_command

logging.basicConfig(level=logging.INFO)

def test():
    test_cases = [
        "che ore sono",
        "apri blocco note",
        "esegui automazione fai una torta",
        "alza il volume di 10",
        "mettiti in pausa" # wait, metti in pausa
    ]
    for case in test_cases:
        print(f"Testing: {case}")
        is_cmd, chat_res, voice_res = parse_local_command(case)
        print(f"Result: {is_cmd} | {chat_res} | {voice_res}")
        print("-" * 40)

if __name__ == "__main__":
    test()
