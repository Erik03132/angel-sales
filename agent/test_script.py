import asyncio

import angelochka_core


async def test():
    res = angelochka_core.get_answer('Какие бройлеры есть?', sender_id='test_1234')
    print("RESPONSE:", res)

if __name__ == "__main__":
    asyncio.run(test())
