#!/usr/bin/env python3
"""Обновление Products.astro — 22 товара с ценами из VK (май 2026)"""
import re

PRODUCTS_JS = """
  const productsData = [
    // БРОЙЛЕРЫ
    {
      id: 'cobb500', name: 'КОББ-500', category: 'broilers',
      description: 'Суточные цыплята бройлерного кросса КОББ-500. Мясистость, отличная конверсия корма и стрессоустойчивость. Набирают 2.5 кг за 42 дня.',
      image: '/Kobb.png',
      pricing: [
        { min: 500, price: 80, label: 'От 500 шт — 80 ₽' },
        { min: 100, price: 85, label: 'От 100 шт — 85 ₽' },
        { min: 20, price: 90, label: 'От 20 шт — 90 ₽' },
      ],
      icon: '🐔', color: 'from-yellow-500 to-orange-500'
    },
    {
      id: 'ross308', name: 'РОСС-308', category: 'broilers',
      description: 'Суточные цыплята РОСС-308 — самый популярный кросс в мире. Высочайшая скорость прироста, превосходная конверсия корма.',
      image: '/ROSS308.png',
      pricing: [
        { min: 500, price: 75, label: 'От 500 шт — 75 ₽' },
        { min: 100, price: 80, label: 'От 100 шт — 80 ₽' },
        { min: 20, price: 85, label: 'От 20 шт — 85 ₽' },
      ],
      icon: '🐔', color: 'from-orange-500 to-orange-600'
    },
    // ЦВЕТНЫЕ БРОЙЛЕРЫ / МЯСОЯИЧНЫЕ
    {
      id: 'master-grey', name: 'Мастер Грей', category: 'dual',
      description: 'Цветной бройлер. До 4.5 кг мяса + крупные яйца. Универсальный выбор для подворья.',
      image: '/MasterGray.png',
      pricing: [{ min: 20, price: 65, label: 'От 20 шт — 65 ₽' }],
      icon: '🐓', color: 'from-slate-500 to-gray-600'
    },
    {
      id: 'red-bro', name: 'Ред Бро', category: 'dual',
      description: 'Мясояичные цыплята с красным оперением. Быстрый рост, великолепный вкус мяса.',
      image: '/RedBro.png',
      pricing: [{ min: 20, price: 80, label: 'От 20 шт — 80 ₽' }],
      icon: '🐓', color: 'from-red-500 to-rose-600'
    },
    {
      id: 'goloshejka', name: 'Голошейка (Nacked Nek)', category: 'dual',
      description: 'Мясная голошейная порода из Франции. Жаростойкая птица с диетическим мясом.',
      image: '/Golosheika.png',
      pricing: [{ min: 20, price: 65, label: 'От 20 шт — 65 ₽' }],
      icon: '🐓', color: 'from-orange-600 to-red-700'
    },
    {
      id: 'farm-color', name: 'Farm Color', category: 'dual',
      description: 'Мясояичные цыплята с разнообразным окрасом. Неприхотливые, продуктивные, идеальны для ЛПХ.',
      image: '/FarmColor.png',
      pricing: [{ min: 20, price: 60, label: 'От 20 шт — 60 ₽' }],
      icon: '🐓', color: 'from-amber-500 to-orange-600'
    },
    {
      id: 'griz-bar', name: 'Гриз Бар (Gris Barre)', category: 'dual',
      description: 'Французская мясояичная линия серо-золотистого окраса. Полу-автосексные.',
      image: '/GREEZBAR.png',
      pricing: [{ min: 20, price: 65, label: 'От 20 шт — 65 ₽' }],
      icon: '🐓', color: 'from-gray-600 to-amber-700'
    },
    {
      id: 'adler-silver', name: 'Адлерская серебристая', category: 'dual',
      description: 'Гордость отечественной селекции. Мясистая птица с красивым серебристым оперением.',
      image: '/Adler.png',
      pricing: [{ min: 20, price: 75, label: 'От 20 шт — 75 ₽' }],
      icon: '🐓', color: 'from-slate-400 to-gray-600'
    },
    // НЕСУШКИ (ЯИЧНЫЕ)
    {
      id: 'dominant-102', name: 'Доминант Д-102', category: 'layers',
      description: 'Яичный кросс Доминант Д-102 (192). Высочайшая яйценоскость, крупное коричневое яйцо.',
      image: '/Dominant102.png',
      pricing: [{ min: 20, price: 60, label: 'От 20 шт — 60 ₽' }],
      icon: '🥚', color: 'from-amber-500 to-yellow-500'
    },
    {
      id: 'dominant-107', name: 'Доминант Д-107, Д-849, Д-859', category: 'layers',
      description: 'Эффектные серо-голубые несушки. До 300 яиц/год, неприхотливые, спокойные.',
      image: '/DominantBlue.png',
      pricing: [{ min: 20, price: 75, label: 'От 20 шт — 75 ₽' }],
      icon: '🥚', color: 'from-slate-500 to-slate-700'
    },
    {
      id: 'loman-brown', name: 'Ломан Браун', category: 'layers',
      description: 'Порода №1 среди несушек. 300-320 яиц/год, неприхотливая, несётся даже зимой.',
      image: '/Loman.png',
      pricing: [{ min: 20, price: 60, label: 'От 20 шт — 60 ₽' }],
      icon: '🥚', color: 'from-amber-600 to-yellow-600'
    },
    {
      id: 'petushki-loman', name: 'Петушки Ломан Браун', category: 'layers',
      description: 'Суточные петушки Ломан Браун. Идеальны для откорма на мясо по выгодной цене.',
      image: '/PetushkiLoman.png',
      pricing: [{ min: 20, price: 10, label: 'От 20 шт — 10 ₽' }],
      icon: '🐓', color: 'from-red-600 to-amber-700'
    },
    // ИНДЮШАТА
    {
      id: 'big-6', name: 'Биг-6 (BIG-6)', category: 'turkeys',
      description: 'Тяжёлый английский кросс. Классика мясного индюководства — до 25 кг за 6 месяцев.',
      image: '/Big6.png',
      pricing: [{ min: 10, price: 450, label: 'От 10 шт — 450 ₽' }],
      icon: '🦃', color: 'from-orange-600 to-amber-600'
    },
    {
      id: 'bronze-708', name: 'Бронза-708 (Bronze)', category: 'turkeys',
      description: 'Широкогрудый кросс с красивым бронзовым оперением. Тяжеловес среди цветных индеек.',
      image: '/Bronze.png',
      pricing: [{ min: 10, price: 550, label: 'От 10 шт — 550 ₽' }],
      icon: '🦃', color: 'from-yellow-600 to-orange-700'
    },
    {
      id: 'hybrid-converter', name: 'Хайбрид Конвертер (Hybrid)', category: 'turkeys',
      description: 'Тяжёлый канадский кросс. Индюки-гиганты до 25-30 кг за полгода!',
      image: '/Konverter.png',
      pricing: [{ min: 10, price: 500, label: 'От 10 шт — 500 ₽' }],
      icon: '🦃', color: 'from-red-500 to-orange-600'
    },
    {
      id: 'grade-maker', name: 'Грейд Мейкер (Grade Maker)', category: 'turkeys',
      description: 'Средне-тяжёлый французский кросс. Привлекательная тушка 15-20 кг, устойчив к инфекциям.',
      image: '/GrayMaker.png',
      pricing: [{ min: 10, price: 450, label: 'От 10 шт — 450 ₽' }],
      icon: '🦃', color: 'from-amber-600 to-yellow-600'
    },
    // УТЯТА
    {
      id: 'duck-mulard', name: 'Утята Мулард', category: 'ducks',
      description: 'Гибрид мускусной и пекинской утки. До 4-5 кг за 2 месяца, нежирное мясо.',
      image: '/Mulard.png',
      pricing: [{ min: 10, price: 250, label: 'От 10 шт — 250 ₽' }],
      icon: '🦆', color: 'from-cyan-500 to-teal-600'
    },
    {
      id: 'duck-agidel', name: 'Утята Агидель', category: 'ducks',
      description: 'Белая мясная утка бройлерного кросса. До 3 кг за 40 дней, пониженное содержание жира.',
      image: '/Agidel.png',
      pricing: [{ min: 10, price: 55, label: 'От 10 шт — 55 ₽' }],
      icon: '🦆', color: 'from-blue-500 to-cyan-500'
    },
    {
      id: 'blue-favorit', name: 'Голубой фаворит', category: 'ducks',
      description: 'Крупная мясная утка эффектного серо-голубого окраса. Неприхотлива.',
      image: '/BlueFavorit.png',
      pricing: [{ min: 10, price: 85, label: 'От 10 шт — 85 ₽' }],
      icon: '🦆', color: 'from-blue-400 to-indigo-500'
    },
    {
      id: 'cherry-velly', name: 'Черри Велли', category: 'ducks',
      description: 'Кросс пекинской утки из Великобритании. Рекордсмен по скорости роста.',
      image: '/CherryVelly.png',
      pricing: [{ min: 10, price: 100, label: 'От 10 шт — 100 ₽' }],
      icon: '🦆', color: 'from-cyan-400 to-blue-500'
    },
    // ГУСЯТА
    {
      id: 'goose-linda', name: 'Гусята Линдовские', category: 'geese',
      description: 'Самая популярная мясная порода в России. Белые гиганты до 9-10 кг. Неприхотливы к климату.',
      image: '/Linda.png',
      pricing: [{ min: 10, price: 300, label: 'От 10 шт — 300 ₽' }],
      icon: '🦢', color: 'from-slate-100 to-gray-300'
    },
    // ЦЕСАРКИ
    {
      id: 'cesarka', name: 'Цесарки', category: 'cesarka',
      description: 'Бройлерная цесарка. Диетическое мясо, гипоаллергенные яйца. Уничтожают колорадского жука!',
      image: '/Cesarka.png',
      pricing: [{ min: 10, price: 120, label: 'От 10 шт — 120 ₽' }],
      icon: '🦤', color: 'from-gray-500 to-slate-500'
    },
  ];
"""

# Читаем файл
with open('src/components/Products.astro', 'r') as f:
    content = f.read()

# Заменяем productsData
old_start = content.find('const productsData = [')
old_end = content.find('];\n\n  let currentProduct', old_start)
if old_start == -1 or old_end == -1:
    print("❌ Не найден productsData"); exit(1)
old_end += 2  # включаем ];

new_content = content[:old_start] + PRODUCTS_JS.strip() + '\n' + content[old_end:]

# Обновляем featuredIds
new_content = new_content.replace(
    "const featuredIds = ['ross308', 'loman-brown', 'hybrid-converter'];",
    "const featuredIds = ['cobb500', 'ross308', 'duck-mulard'];"
)

# Добавляем категорию "Цесарки" в навигацию
if 'data-category="cesarka"' not in new_content:
    new_content = new_content.replace(
        '<button class="category-btn px-6 py-2 rounded-full font-semibold text-sm transition duration-300" data-category="turkeys">',
        '<button class="category-btn px-6 py-2 rounded-full font-semibold text-sm transition duration-300" data-category="cesarka">\n        Цесарки\n      </button>\n      <button class="category-btn px-6 py-2 rounded-full font-semibold text-sm transition duration-300" data-category="turkeys">'
    )

# Добавляем cesarka в categoryLabels
new_content = new_content.replace(
    "turkeys: 'Индюшата'",
    "turkeys: 'Индюшата',\n    cesarka: 'Цесарки'"
)

with open('src/components/Products.astro', 'w') as f:
    f.write(new_content)

print(f"✅ Products.astro обновлён — 22 товара")
