const axios = require('axios');
const fs = require('fs');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../.env') });

const AVITO_CLIENT_ID = process.env.AVITO_CLIENT_ID;
const AVITO_CLIENT_SECRET = process.env.AVITO_CLIENT_SECRET;

async function run() {
    console.log('🚀 Начинаю глубокое сканирование Авито через Node.js...');
    
    try {
        // 1. Получаем токен
        const tokenResp = await axios.post('https://api.avito.ru/token/', 
            new URLSearchParams({
                'client_id': AVITO_CLIENT_ID,
                'client_secret': AVITO_CLIENT_SECRET,
                'grant_type': 'client_credentials'
            }).toString(),
            { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
        );

        const token = tokenResp.data.access_token;
        console.log('✅ Токен получен.');

        const results = {};
        const statuses = ['active', 'old', 'removed'];

        for (const status of statuses) {
            console.log(`📡 Сканирую статус: ${status}...`);
            const itemsResp = await axios.get('https://api.avito.ru/core/v1/items', {
                headers: { 'Authorization': `Bearer ${token}` },
                params: { status: status, per_page: 100 }
            });
            const items = itemsResp.data.resources || [];
            results[status] = items;
            console.log(`   Найдено: ${items.length} шт.`);
        }

        // 2. Сохраняем результат
        const dataPath = path.join(__dirname, '../data/avito/first_deep_scan.json');
        if (!fs.existsSync(path.dirname(dataPath))) {
            fs.mkdirSync(path.dirname(dataPath), { recursive: true });
        }
        fs.writeFileSync(dataPath, JSON.stringify(results, null, 2));
        
        console.log(`\n💾 СКАНИРОВАНИЕ ЗАВЕРШЕНО!`);
        console.log(`Данные сохранены в: data/avito/first_deep_scan.json`);

    } catch (error) {
        console.error('❌ ОШИБКА:', error.response ? error.response.data : error.message);
    }
}

run();
