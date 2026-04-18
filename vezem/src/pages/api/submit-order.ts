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
    const baseWebhook = BITRIX24_WEBHOOK.replace(/\/crm\.(lead|deal)\.add/, '');

    // 1️⃣ СОЗДАЁМ ЛИД (LEAD) с правильной структурой полей
    const leadWebhook = `${baseWebhook}/crm.lead.add`;
    
    // Формируем краткий заголовок
    const itemCount = orderInfo.items.length;
    const totalQuantity = orderInfo.items.reduce((sum: number, item: any) => sum + item.quantity, 0);
    const dealTitle = totalSum > 0 
      ? `Заказ ${orderInfo.name}: ${totalQuantity} шт (${itemCount} поз.) — ${totalSum} ₽`
      : `Заказ ${orderInfo.name}: ${totalQuantity} шт (${itemCount} поз.) — уточнить цену`;
    
    // Форматируем телефон как массив объектов crm_multifield
    const phoneArray = orderInfo.phone ? [{ 
      VALUE: orderInfo.phone, 
      VALUE_TYPE: 'WORK' 
    }] : [];

    const leadData = {
      fields: {
        TITLE: dealTitle,
        NAME: orderInfo.name,
        PHONE: phoneArray,
        ADDRESS: orderInfo.address,
        COMMENTS: fullOrderDescription,
        SOURCE_ID: 'WEB',
        ASSIGNED_BY_ID: 1,
        // Дополнительные поля
        OPPORTUNITY: totalSum,
        CURRENCY_ID: 'RUB',
      }
    };
    
    let leadResponse;
    try {
      leadResponse = await fetch(leadWebhook, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(leadData),
      });
      
      const leadResult = await leadResponse.json();

      if (!leadResponse.ok || leadResult.error) {
        console.error('❌ Ошибка создания лида в Bitrix24:', leadResult);
        return new Response(
          JSON.stringify({ 
            error: leadResult.error_description || leadResult.error || 'Ошибка создания лида',
            details: leadResult
          }),
          { status: 400, headers: { 'Content-Type': 'application/json' } }
        );
      }

      const leadId = leadResult.result;

      // 2️⃣ ДОБАВЛЯЕМ ТОВАРЫ К ЛИДУ
      if (orderInfo.items && orderInfo.items.length > 0) {
        const productRowsWebhook = `${baseWebhook}/crm.lead.productrows.set`;
        
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
          id: leadId,
          rows: productRows
        };

        const productResponse = await fetch(productRowsWebhook, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(productData),
        });

        const productResult = await productResponse.json();

        if (!productResult.result) {
          console.warn('⚠️ Товары не добавлены:', productResult);
        }
      }

      return new Response(
        JSON.stringify({ 
          success: true, 
          message: '✅ Заказ успешно отправлен в Bitrix24',
          leadId: leadId,
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
