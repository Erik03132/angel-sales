from angelochka_core import get_answer


def main():
    query = "[СИСТЕМНАЯ РОЛЬ: CUSTOMER. Товар из объявления: Суточные цыплята росс-308 / С вакцинацией - 75 руб] Добрый вечер.я могу купить у вас 130 шт цыплят? И сколько будет стоить?"
    
    # Синхронный вызов, так как get_answer у нас нигде не declared async, он делает вызовы requests внутри _call_openrouter и т.д.
    answer = get_answer(query, history=[], sender_id="test_user", sender_name="Мамбетова КсеньЯ")
    
    print("\n\n=== ОТВЕТ АНЖЕЛЫ ===\n")
    print(answer)

if __name__ == "__main__":
    main()
