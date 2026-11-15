# CryptoMonitor

Мобільний додаток на **React Native (Expo)** для моніторингу криптовалют:

- Список **топ-20 криптовалют** з API [CoinGecko](https://www.coingecko.com/en/api) (за капіталізацією).
- **Графік зміни ціни** для будь-якої монети (інтервали 1Д / 7Д / 30Д / 90Д / 1Р).
- **Пошук** монети за назвою або символом.
- **Додавання в обране** — список зберігається на пристрої через AsyncStorage.

## Стек

| Шар | Технологія |
| --- | --- |
| Каркас | Expo SDK 51 (React Native 0.74) |
| Навігація | `@react-navigation/native`, `bottom-tabs`, `native-stack` |
| HTTP | `fetch` (без додаткових бібліотек) |
| Графіки | `react-native-chart-kit` + `react-native-svg` |
| Сховище | `@react-native-async-storage/async-storage` |
| Іконки | `@expo/vector-icons` (Ionicons) |
| Безпечні зони | `react-native-safe-area-context` |

## Структура проєкту

```
CryptoMonitor/
├── App.js                       # вхідна точка: провайдери + навігація
├── app.json                     # конфіг Expo
├── babel.config.js
├── index.js
├── package.json
└── src/
    ├── api/
    │   └── coingecko.js         # клієнт CoinGecko (топ, пошук, графік)
    ├── components/
    │   └── CoinListItem.js      # рядок монети у списках
    ├── context/
    │   └── FavoritesContext.js  # обране + AsyncStorage
    ├── screens/
    │   ├── HomeScreen.js        # топ-20 з оновленням
    │   ├── SearchScreen.js      # пошук з debounce
    │   ├── FavoritesScreen.js   # список обраного
    │   └── DetailScreen.js      # деталі + графік + статистика
    └── theme/
        └── colors.js            # темна тема
```

## Запуск

Потрібен Node.js ≥ 18.

```bash
git clone <URL цього репозиторію>
cd CryptoMonitor
npm install --legacy-peer-deps
npx expo start
```

Далі:

- натисніть `w` у консолі — відкрити **в браузері** (web-збірка);
- натисніть `i` / `a` — запустити у симуляторі iOS / Android;
- або зіскануйте QR-код у застосунку **Expo Go** на телефоні.

## API

Використовується безкоштовний публічний CoinGecko API (без ключа):

| Призначення | Endpoint |
| --- | --- |
| Топ-20 за капіталізацією | `GET /coins/markets?vs_currency=usd&order=market_cap_desc&per_page=20` |
| Оновлення обраного | `GET /coins/markets?ids=<id1,id2,...>` |
| Пошук | `GET /search?query=<text>` |
| Графік ціни | `GET /coins/{id}/market_chart?vs_currency=usd&days={1\|7\|30\|90\|365}` |
