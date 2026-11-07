import json

from openai import Client

from emb_api import EmbeddingClient, SearchIndex, search_tool_schemas
from rich import print


client = Client(base_url="http://127.0.0.1:9931/v1", api_key="dummy")
MODEL = "llm"

eclient = EmbeddingClient("http://127.0.0.1:9931/v1", "embeddinggemma2")
idx = SearchIndex("embeddings.db", client=eclient)

TOOLS = {
    "search_text": idx.search_text,
    "search_image": idx.search_image,
    "search_substring": idx.search_substring,
    "search_fuzzy": idx.search_fuzzy,
}

messages = [
    {
        "role": "system",
        "content": "You are a recipe creator agent. User says a query. You GOAL is "
        "1. examine, what items QUERY may be made of\n"
        "2. Separately for each item: query search for it to find something like it in modpack\n"
        "3. Filter output and query missing and incorrect items\n"
        "4. Return items in crafting table grid:\n"
        "top left crafting grid slot; top middle; top right \\n \n"
        'middle left; middle middle; middle right \\n\ndown left; down middle; down right. \\n\n For empty slots use "-"\n'
        "You DO NOT HAVE completed recipes in search, only items. DO NOT QUERY RECIPE'S RESULT OR MULTIPLE ITEMS IN ONE SEARCH CALL\n"
        "QUERY is completely new item recipe and you WILL NOT found any correct results by just search_text(user query). Examine about possible ingredients and ground by searching real ones.",
    }
]
print("Просто пиши запрос. Пустая строка / Ctrl-D — выход.")

while True:
    try:
        user = input("you> ").strip()
    except EOFError, KeyboardInterrupt:
        break
    if not user:
        break

    messages.append({"role": "user", "content": user})

    while True:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=search_tool_schemas(),
        )
        msg = resp.choices[0].message
        print(f"[bright_black]{msg.reasoning_content}")

        assistant = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
        messages.append(assistant)

        if not msg.tool_calls:
            print(f"bot> {msg.content or ''}\n")
            break

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
                result = [hit.as_dict() for hit in TOOLS[name](**args)]
            except Exception as e:
                result = {"error": str(e)}

            print(f"  [{name}] {tc.function.arguments}")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
            print(f"[magenta]{json.dumps(result, ensure_ascii=False)}")
