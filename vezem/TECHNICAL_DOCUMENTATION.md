# ВезёмЦыплят - Техническая документация проекта

## 📋 Оглавление
1. [Обзор проекта](#обзор-проекта)
2. [Архитектура](#архитектура)
3. [Технологический стек](#технологический-стек)
4. [Структура проекта](#структура-проекта)
5. [Компоненты и их функции](#компоненты-и-их-функции)
6. [Функциональность](#функциональность)
7. [Интеграции](#интеграции)
8. [Сборка и развёртывание](#сборка-и-развёртывание)

---

## 📌 Обзор проекта

**ВезёмЦыплят** - это веб-приложение электронной коммерции для продажи молодняка птицы (цыплята, утята, гусята, индюшата) с интеграцией CRM системы Bitrix24 для управления заказами.

**Целевая аудитория:**
- Фермеры и птицеводы
- Владельцы подсобных хозяйств
- Сельскохозяйственные предприятия

**География доставки:**
- Ставропольский край
- Краснодарский край
- Республика Адыгея
- Ростовская область

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────┐
│                   Клиент (Browser)                  │
│         (HTML/CSS/JavaScript - Astro Components)    │
└────────────────────┬────────────────────────────────┘
                     │ HTTPS
                     ↓
┌─────────────────────────────────────────────────────┐
│         Nginx (Reverse Proxy + SSL)                 │
│         185.39.206.145:80/443                       │
└────────────────────┬────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────┐
│      Node.js Server (Express.js)                    │
│      localhost:3000                                 │
│   ┌──────────────────────────────────────────┐      │
│   │ - Статические файлы (dist/client)       │      │
│   │ - API эндпоинты (/api/submit-order)     │      │
│   │ - SPA маршрутизация                      │      │
│   └──────────────────────────────────────────┘      │
└────────────────────┬────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ↓            ↓            ↓
    Файлы      Bitrix24      Yandex.Metrika
   /var/www    CRM API       Аналитика
```

---

## 💻 Технологический стек

### Frontend
| Компонент | Технология | Версия | Назначение |
|-----------|-----------|--------|-----------|
| **Framework** | Astro | 5.14.6 | Статический генератор сайтов |
| **UI компоненты** | Astro Components | - | Переиспользуемые компоненты |
| **Стили** | Tailwind CSS | 3.4.1 | Утилитарный CSS framework |
| **Иконки** | astro-icon | 1.1.1 | SVG иконки |
| **Адаптер** | @astrojs/node | - | Серверный рендеринг |

### Backend
| Компонент | Технология | Версия | Назначение |
|-----------|-----------|--------|-----------|
| **Runtime** | Node.js | 20.19.5 | JavaScript runtime |
| **Web Server** | Express.js | 4.21.2 | HTTP сервер |
| **HTTP запросы** | node-fetch | 2.7.0 | Fetch API для Node.js |
| **Сжатие** | compression | 1.7.4 | Gzip сжатие ответов |

### DevOps и Production
| Компонент | Технология | Версия | Назначение |
|-----------|-----------|--------|-----------|
| **Package Manager** | npm | 11.4.2 | Управление зависимостями |
| **Process Manager** | PM2 | 5.4.3 | Управление процессами |
| **Web Server** | Nginx | 1.26.2 | Reverse proxy, SSL |
| **SSL** | Let's Encrypt | - | HTTPS сертификаты |
| **CRM** | Bitrix24 REST API | - | Управление заказами |
| **Аналитика** | Yandex.Metrika | 104797281 | Отслеживание посещений |

---

## 📁 Структура проекта

```
vezem/
├── 📄 Package.json                 # Зависимости и скрипты
├── 📄 astro.config.mjs             # Конфигурация Astro
├── 📄 tsconfig.json                # Конфигурация TypeScript
├── 📄 tailwind.config.mjs           # Конфигурация Tailwind CSS
├── 📄 server.js                    # Express сервер (production)
├── 📄 ecosystem.config.cjs         # PM2 конфигурация
│
├── 📁 src/
│   ├── 📁 layouts/
│   │   └── Layout.astro            # Главный layout (HTML scaffold + Яндекс Метрика)
│   │
│   ├── 📁 pages/
│   │   ├── index.astro             # Главная страница
│   │   └── 📁 api/
│   │       └── submit-order.ts     # API эндпоинт для заказов
│   │
│   ├── 📁 components/
│   │   ├── Header.astro            # Навигационное меню + мобильное меню
│   │   ├── Welcome.astro           # Hero секция с CTA
│   │   ├── Products.astro          # Каталог товаров (фильтрация, карусель)
│   │   ├── OrderForm.astro         # Модальная форма заказа
│   │   ├── FloatingCart.astro      # Плавающая корзина + управление товарами
│   │   ├── Features.astro          # Преимущества компании
│   │   ├── CTA.astro               # Отзывы клиентов + Call-to-action
│   │   ├── Footer.astro            # Подвал + контакты + модальные окна
│   │   ├── GlobalParticles.astro   # Фоновые частицы (эффекты)
│   │   ├── Toast.astro             # Всплывающие уведомления
│   │   └── SEOSchemas.astro        # JSON-LD структурированные данные
│   │
│   ├── 📁 styles/
│   │   └── global.css              # Глобальные стили
│   │
│   └── 📁 assets/
│       ├── astro.svg               # Логотип Astro
│       ├── background.svg          # Фоновые элементы
│       └── astro.svg               # SVG асеты
│
├── 📁 public/
│   ├── favicon.svg                 # Иконка сайта (курица)
│   ├── Hero.png                    # Главное изображение
│   ├── *.png                       # Изображения птицы
│   │   ├── ROSS308.png             # Бройлер
│   │   ├── Kobb.png                # Бройлер
│   │   ├── Loman.png               # Ломан Браун (несушка)
│   │   ├── Haiseks.png             # Хайсекс (несушка)
│   │   ├── MasterGray.png          # Мастер Грей (мясояичный)
│   │   ├── RedBro.png              # Ред Бро (мясояичный)
│   │   ├── GREEZBAR.png            # Гриз Бар (мясояичный)
│   │   ├── Golosheika.png          # Голошейка (мясояичный)
│   │   ├── Adler.png               # Адлерская серебристая (мясояичный)
│   │   ├── Agidel.png              # Агидель (утята)
│   │   ├── Mulard.png              # Мулард (утята)
│   │   ├── Myskus.png              # Мускусная (утята)
│   │   ├── Linda.png               # Линда (гусята)
│   │   ├── Velikan.png             # Серый великан (гусята)
│   │   ├── Konverter.png           # Хайбрид Конвертер (индюшата)
│   │   ├── Big6.png                # Биг-6 (индюшата)
│   │   ├── GrayMaker.png           # Грейд Мейкер (индюшата)
│   │   └── Bronze.png              # Бронза-708 (индюшата)
│   └── sitemap.xml                 # Карта сайта
│
├── 📁 dist/                        # Сборка (созданная npm run build)
│   ├── 📁 client/                  # Статические файлы
│   │   ├── index.html              # Собранная главная страница
│   │   ├── _astro/                 # Оптимизированный JavaScript и CSS
│   │   └── *.png                   # Изображения птицы
│   └── 📁 server/                  # Серверные файлы для Node.js
│
└── 📄 Документация
    ├── README.md                   # Краткое описание
    ├── DEPLOYMENT_GUIDE.md         # Руководство по развёртыванию
    ├── TECHNICAL_DOCUMENTATION.md  # Этот файл
    └── FEATURES.md                 # Описание возможностей
```

---

## 🧩 Компоненты и их функции

### 1. **Layout.astro** - Главный шаблон
**Функции:**
- Основной HTML скаффолдинг (head, body)
- Подключение глобальных стилей
- SEO теги и JSON-LD схемы
- Яндекс Метрика (ID: 104797281)
- Инициализация компонентов

**Включает:**
- Meta теги (описание, ключевые слова)
- Open Graph (для соцсетей)
- Structured data (LocalBusiness, Organization, FAQPage)

---

### 2. **Header.astro** - Навигация
**Функции:**
- Фиксированная навигационная панель
- Адаптивное меню (Desktop/Mobile)
- Ссылки навигации (Продукция, Контакты, Доставка, Отзывы)
- CTA кнопки (Сроки, Позвонить)
- Мобильное меню с бургер-кнопкой

**Интерактивность:**
- Плавное открытие/закрытие мобильного меню
- Переход к секциям при клике

---

### 3. **Welcome.astro** - Hero секция
**Функции:**
- Главный баннер с изображением
- Привлекающие заголовки и подзаголовки
- CTA кнопки для заказа/просмотра продукции
- Фоновые эффекты и градиенты

---

### 4. **Products.astro** - Каталог товаров
**Функции:**
- Отображение 20+ видов птицы
- Фильтрация по категориям:
  - Бройлеры
  - Несушки
  - Мясояичные
  - Утята
  - Гусята
  - Индюшата
- Карточки товаров с изображением и описанием
- Модальное окно с детальной информацией
- Таблица цен (масштабные скидки)
- Добавление в корзину

**Данные:**
```javascript
const productsData = [
  {
    id: 'ross308',
    name: 'РОСС-308',
    category: 'broilers',
    description: '...',
    image: '/ROSS308.png',
    pricing: [
      { min: 1000, price: 65 },
      { min: 500, price: 70 },
      // ...
    ]
  },
  // ... еще 19 видов
]
```

---

### 5. **OrderForm.astro** - Форма заказа
**Функции:**
- Форма заказа товаров
- Поля: имя, телефон, адрес, комментарий
- Выбор количества товара
- Отправка данных на API

**API эндпоинт:** `POST /api/submit-order`

---

### 6. **FloatingCart.astro** - Плавающая корзина
**Функции:**
- Плавающая кнопка с иконкой корзины
- Отображение количества товаров
- Клик открывает окно с товарами в корзине
- Функции удаления и изменения количества
- Расчёт общей суммы
- Кнопка оформления заказа

**Хранение:** LocalStorage браузера

---

### 7. **Features.astro** - Преимущества
**Функции:**
- 6 карточек с преимуществами:
  - ✅ Качество птицы
  - ✅ Доставка
  - ✅ Гарантия
  - ✅ Ветконтроль
  - ✅ Опыт
  - ✅ Цены

---

### 8. **CTA.astro** - Отзывы и призыв
**Функции:**
- Карусель отзывов клиентов (8 отзывов)
- Рейтинги (5 звёзд)
- Информация о клиентах (имя, регион)
- Навигация по отзывам (стрелки)
- Регионы: Краснодарский край, Ставропольский край, Адыгея, Ростовская область

---

### 9. **Footer.astro** - Подвал
**Функции:**
- Контактная информация
- Времена работы
- Социальные сети
- Модальные окна:
  - Политика конфиденциальности
  - Условия использования
  - Информация о доставке
- Ссылка на Bitrix24

---

### 10. **GlobalParticles.astro** - Фоновые эффекты
**Функции:**
- Анимированные частицы на фоне
- Canvas-based визуализация
- Создает атмосферу и визуальный интерес

---

### 11. **Toast.astro** - Уведомления
**Функции:**
- Всплывающие уведомления (уведомления, ошибки, успех)
- Автоматическое скрытие через 3 секунды
- Анимации появления/исчезновения

---

## 🎯 Функциональность

### 1. Просмотр каталога
- **Процесс:**
  1. Пользователь заходит на сайт
  2. Видит каталог товаров по категориям
  3. Может отфильтровать по типу птицы
  4. Кликает на товар → открывается модаль с деталями
  5. Видит полное описание, цены, прайс-листы

### 2. Добавление в корзину
- **Процесс:**
  1. В модали товара выбирает количество
  2. Видит итоговую цену (с учётом скидок)
  3. Кликает "В корзину"
  4. Товар добавляется в LocalStorage
  5. Плавающая корзина обновляется

### 3. Оформление заказа
- **Процесс:**
  1. Кликает на плавающую корзину
  2. Видит все товары в корзине
  3. Кликает "Оформить заказ"
  4. Заполняет форму (имя, телефон, адрес, комментарий)
  5. Отправляет форму
  6. API отправляет данные в Bitrix24 CRM

### 4. Отслеживание аналитики
- **Yandex.Metrika отслеживает:**
  - Все визиты и сеансы
  - Клики по ссылкам и кнопкам
  - Движения мыши и скроллы
  - События заказов
  - Отскоки

---

## 🔗 Интеграции

### 1. Bitrix24 CRM
**URL:** `https://vezemcip.bitrix24.ru`

**Функция:** Автоматическое создание лидов при заказе

**Параметры:**
```
Webhook URL: https://vezemcip.bitrix24.ru/rest/1/cwill2a1sdpyntll/crm.lead.add
Метод: POST
Поля:
  - NAME: имя клиента
  - PHONE: телефон
  - ADDRESS: адрес доставки
  - COMMENT: комментарий
  - ITEMS: список товаров
```

### 2. Yandex.Metrika
**ID:** `104797281`

**Отслеживание:**
- Webvisor (запись сеансов)
- Clickmap (тепловая карта кликов)
- Ecommerce события
- Отслеживание отскоков

---

## 🔨 Сборка и развёртывание

### Local Development
```bash
# Установка зависимостей
npm install

# Dev сервер
npm run dev

# Сборка статического сайта
npm run build

# Preview production build локально
npm run preview
```

### Production Server Setup

**Server:** Ubuntu Linux + Node.js 20.19.5

**Этапы развёртывания:**

1. **Сборка проекта:**
```bash
npm run build
```

2. **Копирование на сервер:**
```bash
# Загрузить dist.zip на сервер через WinSCP
scp dist.zip root@185.39.206.145:/var/www/vezemcip/
```

3. **Распаковка на сервере:**
```bash
cd /var/www/vezemcip/
unzip -o dist.zip
npm install
```

4. **PM2 конфигурация:**
```javascript
// ecosystem.config.cjs
module.exports = {
  apps: [{
    name: 'vezemcip',
    script: './server.js',
    instances: 1,
    env: {
      NODE_ENV: 'production',
      BITRIX24_WEBHOOK: 'https://vezemcip.bitrix24.ru/rest/1/cwill2a1sdpyntll/crm.lead.add'
    }
  }]
};
```

5. **Запуск через PM2:**
```bash
pm2 start ecosystem.config.cjs
pm2 save
pm2 startup
```

6. **Nginx конфигурация:**
```nginx
server {
    listen 80;
    listen 443 ssl http2;
    server_name vezemcip.ru www.vezemcip.ru;
    
    ssl_certificate /etc/letsencrypt/live/vezemcip.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vezemcip.ru/privkey.pem;
    
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

7. **SSL сертификат (Let's Encrypt):**
```bash
certbot certonly --standalone -d vezemcip.ru -d www.vezemcip.ru
certbot renew --dry-run  # Проверка автообновления
```

---

## 🚀 Server.js - Express Server

**Функции:**
- Обслуживание статических файлов (`dist/client`)
- API эндпоинт `POST /api/submit-order`
- Fallback маршрутизация для SPA
- Gzip сжатие

**Порт:** 3000

**Запуск:**
```bash
node server.js
```

---

## 📊 Поток данных заказа

```
1. User заполняет форму
            ↓
2. Frontend отправляет POST /api/submit-order
            ↓
3. Express server обрабатывает данные
            ↓
4. Server отправляет данные в Bitrix24 webhook
            ↓
5. Bitrix24 создает новый лид в CRM
            ↓
6. Frontend показывает уведомление об успехе
            ↓
7. Yandex.Metrika регистрирует событие
```

---

## 🔐 Переменные окружения

**Файл:** `ecosystem.config.cjs`

```javascript
env: {
  NODE_ENV: 'production',
  BITRIX24_WEBHOOK: 'https://vezemcip.bitrix24.ru/rest/1/cwill2a1sdpyntll/crm.lead.add'
}
```

---

## 📱 Responsive Design

**Breakpoints:**
- Mobile: < 640px (sm)
- Tablet: 640px - 1024px (md)
- Desktop: > 1024px (lg)

**Tailwind классы используются для адаптации:**
```
sm: (mobile-first approach)
md: tablet
lg: desktop
xl: large desktop
```

---

## 🎨 Дизайн и стили

**Цветовая схема:**
- Основной: синий (#0f172a)
- Акцент: голубой/зелёный (cyan/emerald)
- Текст: белый
- Фон: тёмный градиент

**Шрифты:**
- Заголовки: bold, black (900)
- Текст: regular, semibold

**Эффекты:**
- Backdrop blur (размытие фона)
- Градиенты текста
- Тени (shadow)
- Анимации (transition, animation)

---

## 🐛 Основные логики

### Корзина (FloatingCart.astro)
```javascript
// Добавление товара
function addToCart(id, name, price, qty, requiresQuote) {
  let cart = JSON.parse(localStorage.getItem('cart')) || [];
  cart.push({ id, name, price, qty, requiresQuote });
  localStorage.setItem('cart', JSON.stringify(cart));
}

// Получение корзины
function getCart() {
  return JSON.parse(localStorage.getItem('cart')) || [];
}
```

### API запрос (Products.astro)
```javascript
async function addToCartFromModal() {
  const qty = parseInt(document.getElementById('quantity-input').value);
  // ... обработка и отправка
  window.addToCart(productId, name, price, qty, requiresQuote);
}
```

### Отправка заказа (api/submit-order.ts)
```javascript
POST /api/submit-order
{
  name: "Иван Петров",
  phone: "+7-918-350-02-25",
  address: "Краснодар",
  comment: "...",
  items: [...]
}
```

---

## 📈 Производительность

**Оптимизации:**
- Статическая сборка (SSG)
- Gzip сжатие на сервере
- CSS-in-JS оптимизация (Tailwind)
- Кэширование статических файлов
- Lazy loading изображений

**Размеры:**
- Главная страница: ~50 KB (gzip)
- JavaScript: ~25 KB (gzip)
- CSS: ~15 KB (gzip)

---

## 🔄 Процесс обновления

**Для обновления проекта:**

1. **Локально:**
```bash
cd e:\vezem
npm run build  # Создаёт dist/
```

2. **На сервер:**
```bash
# Архивируем
Compress-Archive -Path dist -DestinationPath dist.zip

# Загружаем через WinSCP на 185.39.206.145:/var/www/vezemcip/
```

3. **На сервере:**
```bash
cd /var/www/vezemcip/
unzip -o dist.zip
pm2 restart vezemcip
```

---

## 📞 Контакты и поддержка

**Телефон:** +7 (918) 350-02-25
**CRM:** https://vezemcip.bitrix24.ru
**Домен:** https://vezemcip.ru

---

**Последнее обновление:** 22 октября 2025
**Статус:** Production Ready ✅
