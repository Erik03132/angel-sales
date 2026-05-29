import type { APIRoute } from 'astro';

export const prerender = false;

export const POST: APIRoute = async ({ request }) => {
  try {
    const BITRIX24_WEBHOOK = import.meta.env.BITRIX24_WEBHOOK;
    
    if (!BITRIX24_WEBHOOK) {
      console.error('❌ Webhook не сконфигурирован');
      return new Response(
        JSON.stringify({ error: '❌ Webhook не сконфигурирован' }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      );
    }

    let body;
    try {
      const text = await request.text();
      body = JSON.parse(text);
    } catch (e) {
      console.error('❌ Ошибка парсинга JSON:', e);
      return new Response(
        JSON.stringify({ error: 'Ошибка парсинга JSON' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const { orderInfo } = body;

    // Формируем список товаров с количеством
    const itemsList = orderInfo.items.map((item: any) => {
      const itemTotal = item.quantity * item.price;
      if (item.price > 0) {
        return `• ${item.name}\n  Количество: ${item.quantity} шт\n  Цена: ${item.price} ₽/шт\n  Сумма: ${itemTotal} ₽`;
      } else {
        return `• ${item.name}\n  Количество: ${item.quantity} шт\n  Цена: требуется уточнение`;
      }
    }).join('\n\n');
    
    // Считаем сумму только по товарам с известной ценой
    const totalSum = orderInfo.items.reduce((sum: number, item: any) => 
      sum + (item.quantity * item.price), 0
    );

    // Подсчитываем товары с неопределенной ценой
    const itemsNeedingQuote = orderInfo.items.filter((item: any) => item.requiresQuote || item.price === 0);
    const quoteLine = itemsNeedingQuote.length > 0 
      ? `\n\n⚠️ ТРЕБУЕТСЯ УТОЧНЕНИЕ ЦЕНЫ:\n${itemsNeedingQuote.map((item: any) => `• ${item.name} (${item.quantity} шт)`).join('\n')}`
      : '';

    const fullOrderDescription = `📋 НОВЫЙ ЗАКАЗ ЧЕРЕЗ САЙТ

👤 Клиент: ${orderInfo.name}
📱 Телефон: ${orderInfo.phone}
📍 Адрес доставки: ${orderInfo.address}

📦 ЗАКАЗАННЫЕ ТОВАРЫ:
${itemsList}

💰 СУММА К ОПЛАТЕ: ${totalSum} ₽${quoteLine}

💬 Комментарий клиента:
${orderInfo.comment || '(не указан)'}`;

    // Получаем базовый URL вебхука
    const baseWebhook = BITRIX24_WEBHOOK.replace(/\/crm\.(lead|deal|contact)\.add/, '');

    // Формируем краткий заголовок
    const itemCount = orderInfo.items.length;
    const totalQuantity = orderInfo.items.reduce((sum: number, item: any) => sum + item.quantity, 0);
    const dealTitle = totalSum > 0 
      ? `Заказ ${orderInfo.name}: ${totalQuantity} шт (${itemCount} поз.) — ${totalSum} ₽`
      : `Заказ ${orderInfo.name}: ${totalQuantity} шт (${itemCount} поз.) — уточнить цену`;

    // Форматируем телефон как массив объектов crm_multifield
    const phoneArray = orderInfo.phone ? [{ 
      VALUE: orderInfo.phone, 
      VALUE_TYPE: 'MOBILE' 
    }] : [];

    // Разбиваем имя на части
    const nameParts = (orderInfo.name || 'Клиент').split(' ');
    const firstName = nameParts[0];
    const lastName = nameParts.length > 1 ? nameParts.slice(1).join(' ') : '';

    try {
      // 1️⃣ СОЗДАЁМ КОНТАКТ (CONTACT)
      const contactWebhook = `${baseWebhook}/crm.contact.add`;
      const contactData = {
        fields: {
          NAME: firstName,
          LAST_NAME: lastName,
          PHONE: phoneArray,
          SOURCE_ID: 'WEB',
          OPENED: 'Y',
        }
      };

      const contactResponse = await fetch(contactWebhook, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(contactData),
      });

      const contactResult = await contactResponse.json();
      let contactId: number | null = null;

      if (contactResponse.ok && !contactResult.error) {
        contactId = contactResult.result;
        console.log(`✅ Контакт создан (ID: ${contactId}): ${orderInfo.name}`);
      } else {
        console.warn('⚠️ Не удалось создать контакт:', contactResult);
        // Продолжаем без контакта — сделку всё равно создаём
      }

      // 2️⃣ СОЗДАЁМ СДЕЛКУ (DEAL) — STAGE_ID="NEW" для автодозвона
      const dealWebhook = `${baseWebhook}/crm.deal.add`;
      const dealFields: Record<string, any> = {
        TITLE: dealTitle,
        STAGE_ID: 'NEW',
        SOURCE_ID: 'WEB',
        ASSIGNED_BY_ID: 1,
        OPPORTUNITY: totalSum,
        CURRENCY_ID: 'RUB',
        COMMENTS: fullOrderDescription,
        OPENED: 'Y',
        // Дата поставки — для автодозвона за 1 день
        ...(orderInfo.deliveryDate ? { CLOSEDATE: orderInfo.deliveryDate } : {}),
      };

      if (contactId) {
        dealFields.CONTACT_ID = contactId;
      }

      const dealData = { fields: dealFields };

      const dealResponse = await fetch(dealWebhook, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dealData),
      });

      const dealResult = await dealResponse.json();

      if (!dealResponse.ok || dealResult.error) {
        console.error('❌ Ошибка создания сделки в Bitrix24:', dealResult);
        return new Response(
          JSON.stringify({ 
            error: dealResult.error_description || dealResult.error || 'Ошибка создания сделки',
            details: dealResult
          }),
          { status: 400, headers: { 'Content-Type': 'application/json' } }
        );
      }

      const dealId = dealResult.result;
      console.log(`✅ Сделка создана (ID: ${dealId}): ${dealTitle}`);

      // 3️⃣ ДОБАВЛЯЕМ ТОВАРЫ К СДЕЛКЕ
      if (orderInfo.items && orderInfo.items.length > 0) {
        const productRowsWebhook = `${baseWebhook}/crm.deal.productrows.set`;
        
        const productRows = orderInfo.items.map((item: any, index: number) => ({
          PRODUCT_NAME: item.name,
          PRICE: item.price,
          QUANTITY: item.quantity,
          DISCOUNT_TYPE_ID: 1, // Абсолютное значение
          DISCOUNT_SUM: 0,
          TAX_RATE: 0,
          TAX_INCLUDED: 'N',
          SORT: (index + 1) * 10
        }));

        const productData = {
          id: dealId,
          rows: productRows
        };

        const productResponse = await fetch(productRowsWebhook, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(productData),
        });

        const productResult = await productResponse.json();

        if (!productResult.result) {
          console.warn('⚠️ Товары не добавлены к сделке:', productResult);
        }
      }

      return new Response(
        JSON.stringify({ 
          success: true, 
          message: '✅ Заказ успешно отправлен в Bitrix24',
          dealId: dealId,
          contactId: contactId,
          totalSum: totalSum
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    } catch (error) {
      console.error('❌ Ошибка при отправке заказа:', error);
      return new Response(
        JSON.stringify({ error: 'Ошибка на сервере', details: String(error) }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      );
    }
  } catch (error) {
    console.error('❌ Критическая ошибка при обработке заказа:', error);
    return new Response(
      JSON.stringify({ error: 'Критическая ошибка на сервере' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
};
