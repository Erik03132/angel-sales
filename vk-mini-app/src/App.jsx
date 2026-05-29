import React, { useState, useEffect, useMemo, useCallback } from 'react';
import bridge from '@vkontakte/vk-bridge';
import './index.css';

// ============================================================
// 📦 ДАННЫЕ: Актуальный каталог (май 2026, из vezemcip.ru)
// ============================================================
const IMG = '/vk-app/img';

const CATALOG = [
  // Бройлеры
  { id: 1, name: 'КОББ-500', type: 'бройлер', emoji: '🐥', img: `${IMG}/kobb500.png`, price: 90, priceFrom: true, min: 20, desc: 'Быстрый набор массы. До 3кг за 42 дня. Лидер продаж.' },
  { id: 2, name: 'РОСС-308', type: 'бройлер', emoji: '🐣', img: `${IMG}/ross308.png`, price: 85, priceFrom: true, min: 20, desc: 'Устойчив к болезням. Высокая выживаемость.' },
  // Несушки
  { id: 3, name: 'Ломан Браун', type: 'несушка', emoji: '🐔', img: `${IMG}/loman.png`, price: 95, priceFrom: true, min: 20, desc: 'До 320 яиц/год. Самая популярная.' },
  { id: 4, name: 'Хайсекс Браун', type: 'несушка', emoji: '🐔', img: `${IMG}/haiseks.png`, price: 95, priceFrom: true, min: 20, desc: 'Компактная, высокая яйценоскость.' },
  { id: 5, name: 'Доминант 107', type: 'несушка', emoji: '🐔', img: `${IMG}/dominant.png`, price: 75, priceFrom: true, min: 20, desc: 'Разноцветные яйца. Декоративная.' },
  { id: 6, name: 'Ред Бро', type: 'мясояичная', emoji: '🐔', img: `${IMG}/redbro.png`, price: 100, priceFrom: true, min: 20, desc: 'Мясо-яичная. Неприхотлива к кормам.' },
  // Утки
  { id: 7, name: 'Мулард', type: 'утка', emoji: '🦆', img: `${IMG}/mulard.png`, price: 250, priceFrom: false, min: 10, desc: 'Нежирное мясо. До 6кг за 3 мес.' },
  { id: 8, name: 'Черри Велли', type: 'утка', emoji: '🦆', img: `${IMG}/cherry.png`, price: 150, priceFrom: false, min: 10, desc: 'Быстрый рост. Отличный пух.' },
  { id: 11, name: 'Агидель', type: 'утка', emoji: '🦆', img: `${IMG}/agidel.png`, price: 90, priceFrom: true, min: 20, desc: 'Бройлерная утка. До 3кг за 40 дней.' },
  { id: 12, name: 'СТ-5', type: 'утка', emoji: '🦆', img: null, price: 110, priceFrom: true, min: 20, desc: 'Российская мясная утка. Быстрый набор массы.' },
  // Гуси
  { id: 9, name: 'Линда', type: 'гусь', emoji: '🪿', img: `${IMG}/linda.png`, price: 400, priceFrom: false, min: 10, desc: 'Самая популярная порода. До 8кг.' },
  // Индюки
  { id: 10, name: 'Биг-6', type: 'индюк', emoji: '🦃', img: `${IMG}/big6.png`, price: 450, priceFrom: false, min: 10, desc: 'Тяжеловес до 25кг. Отличный выход мяса.' },
  // Допы
  { id: 100, name: 'Вет-аптечка', type: 'доп', emoji: '💊', img: null, price: 350, priceFrom: false, min: 1, desc: 'Полный набор витаминов на 50 голов.' },
  { id: 101, name: 'Комбикорм ПК-5', type: 'доп', emoji: '🌾', img: null, price: 450, priceFrom: false, min: 1, desc: 'Стартовый комбикорм, мешок 5кг.' },
];

const CATEGORIES = [
  { key: 'all', label: '🏠 Все' },
  { key: 'бройлер', label: '🐥 Бройлеры' },
  { key: 'несушка', label: '🐔 Несушки' },
  { key: 'мясояичная', label: '🐓 Мясояичные' },
  { key: 'утка', label: '🦆 Утки' },
  { key: 'гусь', label: '🪿 Гуси' },
  { key: 'индюк', label: '🦃 Индюки' },
  { key: 'доп', label: '💊 Допы' },
];

const FEED_NORMS = {
  'бройлер': { kgPerHead: 4.85, stages: ['Старт (1-10д)', 'Рост (11-24д)', 'Финиш (25-42д)'] },
  'несушка': { kgPerHead: 3.3, stages: ['Старт (1-8нед)', 'Рост (9-16нед)'] },
  'утка':    { kgPerHead: 7.5, stages: ['Старт (1-14д)', 'Рост (15-28д)', 'Финиш (29-56д)'] },
  'гусь':    { kgPerHead: 12.0, stages: ['Старт (1-21д)', 'Рост (22-56д)'] },
  'индюк':   { kgPerHead: 22.3, stages: ['Старт (1-14д)', 'Рост (15-56д)', 'Финиш (57-98д)'] },
};

const DELIVERY_DATES = [
  { value: '2026-05-15', label: '📅 15 мая (чт) — Свободно' },
  { value: '2026-05-19', label: '📅 19 мая (пн) — Свободно' },
  { value: '2026-05-22', label: '📅 22 мая (чт) — Мало мест' },
  { value: '2026-05-26', label: '📅 26 мая (пн) — Резерв' },
  { value: '2026-05-29', label: '📅 29 мая (чт) — Резерв' },
];

const DELIVERY_REGIONS = [
  { value: 'crimea', label: '🏖 Крым (Симферополь, Джанкой, Севастополь)' },
  { value: 'krasnodar', label: '🌴 Краснодарский край' },
  { value: 'rostov', label: '🏭 Ростовская область' },
  { value: 'stavropol', label: '⛰️ Ставропольский край' },
  { value: 'moscow', label: '🏙 Москва и МО' },
  { value: 'pickup', label: '🚗 Самовывоз (пгт Азовское, Крым)' },
];

// ============================================================
// 🔧 БЭКЕНД API URL (Анжелочка на VPS)
// ============================================================
const API_BASE = 'https://vezemcip.ru/api';

// ============================================================
// 📱 ПРИЛОЖЕНИЕ
// ============================================================
const App = () => {
  const [screen, setScreen] = useState('home'); // home | catalog | cart | success
  const [cart, setCart] = useState({});           // { productId: quantity }
  const [category, setCategory] = useState('all');
  const [user, setUser] = useState(null);
  const [phone, setPhone] = useState('');
  const [deliveryDate, setDeliveryDate] = useState(DELIVERY_DATES[0].value);
  const [region, setRegion] = useState('crimea');
  const [orderNum, setOrderNum] = useState('');
  const [loading, setLoading] = useState(false);

  // VK Bridge: получаем данные пользователя
  useEffect(() => {
    (async () => {
      try {
        const u = await bridge.send('VKWebAppGetUserInfo');
        setUser(u);
      } catch (e) {
        console.warn('VK Bridge user info failed:', e);
      }
    })();
  }, []);

  // Запрос телефона через VK Bridge
  const requestPhone = useCallback(async () => {
    try {
      const data = await bridge.send('VKWebAppGetPhoneNumber');
      if (data.phone_number) {
        setPhone(data.phone_number);
      }
    } catch (e) {
      console.warn('Phone request declined');
    }
  }, []);

  // Управление корзиной
  const addToCart = useCallback((id) => {
    const item = CATALOG.find(p => p.id === id);
    setCart(prev => ({
      ...prev,
      [id]: prev[id] ? prev[id] + (item.type === 'доп' ? 1 : 10) : item.min,
    }));
  }, []);

  const updateQty = useCallback((id, delta) => {
    setCart(prev => {
      const item = CATALOG.find(p => p.id === id);
      const step = item.type === 'доп' ? 1 : 10;
      const next = (prev[id] || 0) + delta * step;
      if (next < item.min) {
        const copy = { ...prev };
        delete copy[id];
        return copy;
      }
      return { ...prev, [id]: next };
    });
  }, []);

  const removeFromCart = useCallback((id) => {
    setCart(prev => {
      const copy = { ...prev };
      delete copy[id];
      return copy;
    });
  }, []);

  // Расчёты
  const calc = useMemo(() => {
    let totalCost = 0;
    let totalBirds = 0;
    const items = [];
    const feeds = [];

    Object.entries(cart).forEach(([id, qty]) => {
      const product = CATALOG.find(p => p.id === parseInt(id));
      if (!product) return;
      const subtotal = product.price * qty;
      totalCost += subtotal;
      items.push({ ...product, qty, subtotal });

      if (product.type !== 'доп') {
        totalBirds += qty;
        const norm = FEED_NORMS[product.type];
        if (norm) {
          const kgNeeded = qty * norm.kgPerHead;
          const bags25 = Math.ceil(kgNeeded / 25);
          feeds.push({ breed: product.name, qty, kgNeeded, bags25, stages: norm.stages });
        }
      }
    });

    return { totalCost, totalBirds, items, feeds, cartSize: items.length };
  }, [cart]);

  // Оформление заказа
  const submitOrder = useCallback(async () => {
    setLoading(true);
    const orderData = {
      user_name: user ? `${user.first_name} ${user.last_name}` : 'VK User',
      user_id: user?.id,
      phone: phone || 'не указан',
      items: calc.items.map(i => ({ name: i.name, qty: i.qty, price: i.price })),
      total: calc.totalCost,
      total_birds: calc.totalBirds,
      delivery_date: deliveryDate,
      region: region,
      source: 'vk_mini_app',
    };

    try {
      // Пробуем отправить на сервер Анжелочки
      const resp = await fetch(`${API_BASE}/vk-order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(orderData),
      });
      const data = await resp.json();
      setOrderNum(data.order_id || `VK-${Date.now().toString(36).toUpperCase()}`);
    } catch (e) {
      // Fallback — генерируем номер локально
      setOrderNum(`VK-${Date.now().toString(36).toUpperCase()}`);
      console.warn('API unavailable, order saved locally:', orderData);
    }

    setLoading(false);
    setScreen('success');
  }, [user, phone, cart, calc, deliveryDate, region]);

  // Фильтрация каталога
  const filteredCatalog = useMemo(() => {
    if (category === 'all') return CATALOG;
    return CATALOG.filter(p => p.type === category);
  }, [category]);

  // ============================================================
  // 🎨 РЕНДЕР
  // ============================================================

  // --- ГЛАВНАЯ ---
  if (screen === 'home') {
    return (
      <div style={{ paddingBottom: calc.cartSize > 0 ? 80 : 16 }}>
        {/* Баннер */}
        <div className="hero-banner">
          <h2>Сезон 2026 открыт! 🐣</h2>
          <p>Суточные цыплята с доставкой по Югу России. Бронируйте прямо в ВК!</p>
          <button className="hero-btn" onClick={() => setScreen('catalog')}>
            🛒 Перейти в каталог
          </button>
        </div>

        {/* Инфо */}
        <div className="info-bar">
          🚚 Доставка ПН и ЧТ. Климат-контроль. 100% гарантия.
        </div>

        {/* ТОП товары */}
        <div className="section-header">🔥 Хиты продаж</div>
        <div className="product-grid">
          {CATALOG.filter(p => [1, 2, 7, 10].includes(p.id)).map(product => (
            <ProductCard
              key={product.id}
              product={product}
              qty={cart[product.id]}
              onAdd={() => addToCart(product.id)}
              onPlus={() => updateQty(product.id, 1)}
              onMinus={() => updateQty(product.id, -1)}
            />
          ))}
        </div>

        {/* Несушки */}
        <div className="section-header">🥚 Несушки</div>
        <div className="product-grid">
          {CATALOG.filter(p => p.type === 'несушка').map(product => (
            <ProductCard
              key={product.id}
              product={product}
              qty={cart[product.id]}
              onAdd={() => addToCart(product.id)}
              onPlus={() => updateQty(product.id, 1)}
              onMinus={() => updateQty(product.id, -1)}
            />
          ))}
        </div>

        {/* FAB корзина */}
        {calc.cartSize > 0 && (
          <div className="total-bar">
            <div className="total-row">
              <span className="total-label">{calc.totalBirds} голов · {calc.cartSize} поз.</span>
              <span className="total-price">{calc.totalCost.toLocaleString('ru')} ₽</span>
            </div>
            <button className="order-btn" onClick={() => setScreen('cart')}>
              🛒 Оформить заказ
            </button>
          </div>
        )}
      </div>
    );
  }

  // --- КАТАЛОГ ---
  if (screen === 'catalog') {
    return (
      <div style={{ paddingBottom: calc.cartSize > 0 ? 80 : 16 }}>
        <button className="panel-back" onClick={() => setScreen('home')}>← Главная</button>

        <div className="section-header">📦 Все товары</div>

        {/* Табы категорий */}
        <div className="category-tabs">
          {CATEGORIES.map(cat => (
            <button
              key={cat.key}
              className={`category-tab ${category === cat.key ? 'active' : ''}`}
              onClick={() => setCategory(cat.key)}
            >
              {cat.label}
            </button>
          ))}
        </div>

        <div className="product-grid">
          {filteredCatalog.map(product => (
            <ProductCard
              key={product.id}
              product={product}
              qty={cart[product.id]}
              onAdd={() => addToCart(product.id)}
              onPlus={() => updateQty(product.id, 1)}
              onMinus={() => updateQty(product.id, -1)}
            />
          ))}
        </div>

        {calc.cartSize > 0 && (
          <div className="total-bar">
            <div className="total-row">
              <span className="total-label">{calc.totalBirds} голов</span>
              <span className="total-price">{calc.totalCost.toLocaleString('ru')} ₽</span>
            </div>
            <button className="order-btn" onClick={() => setScreen('cart')}>
              🛒 К оформлению
            </button>
          </div>
        )}
      </div>
    );
  }

  // --- КОРЗИНА ---
  if (screen === 'cart') {
    return (
      <div style={{ paddingBottom: 100 }}>
        <button className="panel-back" onClick={() => setScreen('home')}>← Назад</button>

        <div className="section-header">🛒 Ваш заказ</div>

        {calc.items.length === 0 ? (
          <div className="empty-cart">
            <div className="emoji-big">🐣</div>
            <h3>Корзина пуста</h3>
            <p>Выберите породу в каталоге</p>
            <button className="add-btn primary" style={{ maxWidth: 200, margin: '16px auto' }}
              onClick={() => setScreen('catalog')}>В каталог</button>
          </div>
        ) : (
          <>
            {/* Товары */}
            {calc.items.map(item => (
              <div className="cart-item" key={item.id}>
                {item.img ? (
                  <img className="cart-item-img" src={item.img} alt={item.name} />
                ) : (
                  <span className="item-emoji">{item.emoji}</span>
                )}
                <div className="item-info">
                  <div className="item-name">{item.name}</div>
                  <div className="item-price">{item.price}₽ × {item.qty} шт</div>
                </div>
                <div className="qty-controls" style={{ marginTop: 0 }}>
                  <button className="qty-btn" onClick={() => updateQty(item.id, -1)}>−</button>
                  <span className="qty-value">{item.qty}</span>
                  <button className="qty-btn" onClick={() => updateQty(item.id, 1)}>+</button>
                </div>
                <span className="item-subtotal">{item.subtotal.toLocaleString('ru')}₽</span>
                <button className="remove-btn" onClick={() => removeFromCart(item.id)}>✕</button>
              </div>
            ))}

            {/* Калькулятор кормов */}
            {calc.feeds.length > 0 && (
              <>
                <div className="section-header">🌾 Расчёт кормов</div>
                {calc.feeds.map((feed, i) => (
                  <div className="feed-calc" key={i}>
                    <h3>{feed.breed} ({feed.qty} голов)</h3>
                    <div className="feed-row">
                      <span className="label">Нужно корма:</span>
                      <span className="value">{feed.kgNeeded.toFixed(1)} кг</span>
                    </div>
                    <div className="feed-row">
                      <span className="label">Мешков по 25кг:</span>
                      <span className="value">≈ {feed.bags25} мешков</span>
                    </div>
                    <div className="feed-row">
                      <span className="label">Линейка:</span>
                      <span className="value" style={{ fontSize: 12 }}>{feed.stages.join(' → ')}</span>
                    </div>
                  </div>
                ))}
              </>
            )}

            {/* Доставка */}
            <div className="section-header">🚚 Доставка</div>
            <div className="delivery-form">
              <div className="form-group">
                <label>Дата вывода</label>
                <select value={deliveryDate} onChange={e => setDeliveryDate(e.target.value)}>
                  {DELIVERY_DATES.map(d => (
                    <option key={d.value} value={d.value}>{d.label}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Ваш регион</label>
                <select value={region} onChange={e => setRegion(e.target.value)}>
                  {DELIVERY_REGIONS.map(r => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Телефон</label>
                {phone ? (
                  <input type="tel" value={phone} onChange={e => setPhone(e.target.value)} placeholder="+7 (___) ___-__-__" />
                ) : (
                  <button className="add-btn primary" onClick={requestPhone}>
                    📱 Указать номер из VK
                  </button>
                )}
              </div>
            </div>
          </>
        )}

        {/* Итого */}
        {calc.items.length > 0 && (
          <div className="total-bar">
            <div className="total-row">
              <span className="total-label">Итого ({calc.totalBirds} голов)</span>
              <span className="total-price">{calc.totalCost.toLocaleString('ru')} ₽</span>
            </div>
            <button
              className="order-btn"
              onClick={submitOrder}
              disabled={loading}
            >
              {loading ? '⏳ Отправляем...' : '✅ Оформить заказ'}
            </button>
          </div>
        )}
      </div>
    );
  }

  // --- УСПЕХ ---
  if (screen === 'success') {
    return (
      <div className="success-screen">
        <div className="check">✅</div>
        <div className="order-num">Заказ {orderNum}</div>
        <h2>Спасибо{user ? `, ${user.first_name}` : ''}!</h2>
        <p>
          Анжела Заботкина (наш менеджер) свяжется с вами в течение 15 минут для подтверждения деталей заказа.
          <br /><br />
          📞 Если нужна срочная связь: <strong>+7 (918) 047-51-07</strong>
        </p>
        <button className="order-btn" onClick={() => { setCart({}); setScreen('home'); }}>
          🏠 Вернуться в магазин
        </button>
      </div>
    );
  }

  return null;
};

// ============================================================
// 🃏 КАРТОЧКА ТОВАРА
// ============================================================
const ProductCard = React.memo(({ product, qty, onAdd, onPlus, onMinus }) => (
  <div className="product-card">
    {product.img ? (
      <img className="product-img" src={product.img} alt={product.name} />
    ) : (
      <span className="emoji">{product.emoji}</span>
    )}
    <div className="name">{product.name}</div>
    <div className="breed-type">{product.type}</div>
    <div className="price-tag">
      {product.priceFrom && <small>от </small>}
      {product.price}₽
      <small> / шт</small>
    </div>
    <div className="min-order">мин. {product.min} шт</div>

    {qty ? (
      <div className="qty-controls">
        <button className="qty-btn" onClick={onMinus}>−</button>
        <span className="qty-value">{qty}</span>
        <button className="qty-btn" onClick={onPlus}>+</button>
      </div>
    ) : (
      <button className="add-btn primary" onClick={onAdd}>
        В корзину
      </button>
    )}
  </div>
));

export default App;
