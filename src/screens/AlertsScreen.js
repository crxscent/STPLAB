import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, FlatList, StyleSheet, RefreshControl, Animated } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../theme/colors';
import { fetchAlerts, fetchStats, subscribeAlerts, API_URL } from '../api/stream';

const TYPE_META = {
  WHALE: { icon: 'fish', label: 'Кит', color: colors.primary },
  VOLATILITY: { icon: 'pulse', label: 'Волатильність', color: colors.accent },
  VOLUME_SPIKE: { icon: 'bar-chart', label: 'Сплеск обсягу', color: '#A855F7' },
};
const SEV_COLOR = { CRITICAL: colors.negative, HIGH: '#F97316', MEDIUM: colors.accent, LOW: colors.textMuted };

const fmtUsd = (v) => '$' + Math.round(v).toLocaleString('en-US');
const fmtTime = (iso) => new Date(iso).toLocaleTimeString('uk-UA');

function StatBox({ label, value }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value ?? '—'}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function AlertCard({ item, fresh }) {
  const meta = TYPE_META[item.signal_type] || TYPE_META.WHALE;
  const flash = useRef(new Animated.Value(fresh ? 1 : 0)).current;
  useEffect(() => {
    if (fresh) Animated.timing(flash, { toValue: 0, duration: 1500, useNativeDriver: false }).start();
  }, []);
  const bg = flash.interpolate({ inputRange: [0, 1], outputRange: [colors.card, '#2A3570'] });
  return (
    <Animated.View style={[styles.card, { backgroundColor: bg, borderLeftColor: SEV_COLOR[item.severity] }]}>
      <View style={styles.cardHead}>
        <Ionicons name={meta.icon} size={18} color={meta.color} />
        <Text style={[styles.type, { color: meta.color }]}>{meta.label}</Text>
        <Text style={styles.symbol}>{item.symbol}</Text>
        <Text style={[styles.sev, { color: SEV_COLOR[item.severity] }]}>{item.severity}</Text>
      </View>
      <Text style={styles.msg}>{item.message}</Text>
      <View style={styles.cardFoot}>
        <Text style={styles.foot}>{fmtTime(item.detected_at)}</Text>
        <Text style={styles.foot}>
          {item.side} · {fmtUsd(item.total_usd)} · ціна {Number(item.price).toPrecision(6)}
        </Text>
      </View>
    </Animated.View>
  );
}

export default function AlertsScreen() {
  const [alerts, setAlerts] = useState([]);
  const [stats, setStats] = useState(null);
  const [online, setOnline] = useState(false);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const freshIds = useRef(new Set());

  const load = useCallback(async () => {
    try {
      const [a, s] = await Promise.all([fetchAlerts(50), fetchStats()]);
      setAlerts(a);
      setStats(s);
      setError(null);
    } catch (e) {
      setError(`Сервер ${API_URL} недоступний`);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const statsTimer = setInterval(() => fetchStats().then(setStats).catch(() => {}), 10000);
    const unsub = subscribeAlerts((a) => {
      freshIds.current.add(a.id);
      setAlerts((prev) => [a, ...prev.filter((x) => x.id !== a.id)].slice(0, 200));
    }, setOnline);
    return () => {
      clearInterval(statsTimer);
      unsub();
    };
  }, [load]);

  const c = stats?.anomalies || {};
  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Аномалії</Text>
        <View style={styles.live}>
          <View style={[styles.dot, { backgroundColor: online ? colors.positive : colors.negative }]} />
          <Text style={styles.subtitle}>{online ? 'Live' : 'Offline'}</Text>
        </View>
      </View>
      <View style={styles.stats}>
        <StatBox label="10 хв" value={c.last_10m} />
        <StatBox label="1 год" value={c.last_1h} />
        <StatBox label="24 год" value={c.last_24h} />
      </View>
      {error && <Text style={styles.error}>{error}</Text>}
      <FlatList
        data={alerts}
        keyExtractor={(i) => String(i.id)}
        renderItem={({ item }) => <AlertCard item={item} fresh={freshIds.current.has(item.id)} />}
        contentContainerStyle={{ padding: 12, paddingBottom: 24 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.primary} />}
        ListEmptyComponent={!error && <Text style={styles.empty}>Поки що аномалій немає</Text>}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: 16, paddingTop: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  title: { color: colors.text, fontSize: 28, fontWeight: '700' },
  live: { flexDirection: 'row', alignItems: 'center' },
  dot: { width: 8, height: 8, borderRadius: 4, marginRight: 6 },
  subtitle: { color: colors.textMuted, fontSize: 14 },
  stats: { flexDirection: 'row', paddingHorizontal: 12, paddingTop: 12 },
  stat: { flex: 1, backgroundColor: colors.bgElev, borderColor: colors.border, borderWidth: 1, borderRadius: 12, marginHorizontal: 4, paddingVertical: 10, alignItems: 'center' },
  statValue: { color: colors.text, fontSize: 22, fontWeight: '700' },
  statLabel: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  error: { color: colors.negative, textAlign: 'center', marginTop: 12 },
  empty: { color: colors.textMuted, textAlign: 'center', marginTop: 40 },
  card: { borderRadius: 12, padding: 12, marginBottom: 10, borderLeftWidth: 4, borderColor: colors.border },
  cardHead: { flexDirection: 'row', alignItems: 'center' },
  type: { marginLeft: 6, fontWeight: '600', fontSize: 13 },
  symbol: { color: colors.text, fontWeight: '700', marginLeft: 8, flex: 1 },
  sev: { fontSize: 11, fontWeight: '700' },
  msg: { color: colors.text, marginTop: 6, fontSize: 14 },
  cardFoot: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
  foot: { color: colors.textMuted, fontSize: 12 },
});
