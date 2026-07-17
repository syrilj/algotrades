import json
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from services.market_runtime import (
    CoverageHealth,
    CoverageMode,
    Horizon,
    InstrumentCategory,
    InstrumentClassification,
    LatestTickState,
    Opportunity,
    OpportunityEvidence,
    Tick,
    TickBarAggregator,
    TradePlan,
    classify_horizon,
    evaluate_freshness,
    instrument_from_catalog,
    normalize_category,
    rank_opportunities,
)


UTC = timezone.utc


class MarketRuntimeTestCase(unittest.TestCase):
    def setUp(self):
        self.computed_at = datetime(2026, 7, 13, 10, 1, tzinfo=UTC)

    def instrument(self, symbol="VOD.L", category="stock", **kwargs):
        return instrument_from_catalog(
            symbol=symbol,
            name=kwargs.pop("name", symbol),
            category=category,
            **kwargs,
        )

    def freshness(self, instrument, age_seconds=5):
        return evaluate_freshness(
            instrument,
            market_asof=self.computed_at - timedelta(seconds=age_seconds),
            computed_at=self.computed_at,
            thresholds={instrument.category: timedelta(seconds=30)},
        )

    def plan(self):
        return TradePlan(
            side="buy",
            entry_zone=(99.0, 101.0),
            entry_trigger="Break and hold above 101",
            invalidation="Close below 98",
            stop=98.0,
            targets=(105.0, 110.0),
            trailing_rule=None,
            time_stop="Exit by session close",
        )


class CatalogAndCoverageTests(MarketRuntimeTestCase):
    def test_catalog_categories_are_normalized_and_classified(self):
        tradable = {
            "Common Stocks": InstrumentCategory.STOCK,
            "Exchange Traded Funds": InstrumentCategory.ETF,
            "Foreign Exchange": InstrumentCategory.FX,
            "Cryptocurrencies": InstrumentCategory.CRYPTO,
            "Commodities": InstrumentCategory.COMMODITY,
            "Market Indices": InstrumentCategory.INDEX,
            "Futures": InstrumentCategory.FUTURE,
            "Options": InstrumentCategory.OPTION,
        }
        for raw_category, normalized in tradable.items():
            with self.subTest(raw_category=raw_category):
                self.assertEqual(normalize_category(raw_category), normalized)
                self.assertEqual(
                    self.instrument(category=raw_category).classification,
                    InstrumentClassification.TRADABLE,
                )

        for raw_category in (
            "Economics",
            "Government Bonds",
            "Bond Yields",
            "Interest Rates",
            "Currency Indices",
        ):
            with self.subTest(raw_category=raw_category):
                self.assertEqual(
                    self.instrument(category=raw_category).classification,
                    InstrumentClassification.CONTEXT_ONLY,
                )

        self.assertEqual(
            self.instrument(category="Government Bonds", explicitly_tradable=True).classification,
            InstrumentClassification.TRADABLE,
        )
        self.assertEqual(
            self.instrument(category="Collectible Watches").classification,
            InstrumentClassification.UNSUPPORTED,
        )

    def test_contracts_are_immutable_and_json_serializable(self):
        instrument = self.instrument()
        with self.assertRaises(FrozenInstanceError):
            instrument.symbol = "BARC.L"
        payload = json.loads(instrument.to_json())
        self.assertEqual(payload["category"], "stock")
        self.assertEqual(payload["classification"], "tradable")

    def test_coverage_health_carries_required_counts_and_allowance(self):
        for mode in CoverageMode:
            snapshot = CoverageHealth(
                mode=mode,
                catalog_total=100,
                streamable_total=80,
                subscribed_count=50,
                stale_count=3,
                allowance_ok=False,
                allowance_reason="subscription cap",
                computed_at=self.computed_at,
            )
            self.assertEqual(snapshot.allowance_reason, "subscription cap")
            self.assertIn(mode, {
                CoverageMode.FULL,
                CoverageMode.WARMING,
                CoverageMode.DEGRADED_RANKED,
                CoverageMode.STALE,
            })


class TickStateAndBarTests(MarketRuntimeTestCase):
    def tick(self, seconds, price, size, received_offset=1):
        market_asof = datetime(2026, 7, 13, 10, 0, tzinfo=UTC) + timedelta(seconds=seconds)
        return Tick(
            instrument_id="VOD.L",
            price=price,
            size=size,
            market_asof=market_asof,
            received_at=market_asof + timedelta(seconds=received_offset),
        )

    def test_latest_tick_state_ignores_older_and_duplicate_ticks(self):
        state = LatestTickState()
        current = self.tick(40, 105.0, 2.0)
        older = self.tick(20, 98.0, 3.0)
        duplicate = self.tick(40, 105.0, 2.0, received_offset=5)

        self.assertTrue(state.update(current))
        self.assertFalse(state.update(older))
        self.assertFalse(state.update(duplicate))
        self.assertEqual(state.get("VOD.L"), current)

    def test_aggregates_deterministic_one_and_five_minute_ohlcv(self):
        aggregator = TickBarAggregator(("1m", "5m"))
        ticks = [
            self.tick(10, 100.0, 1.0),
            self.tick(40, 105.0, 2.0),
            self.tick(20, 98.0, 3.0),
            self.tick(299, 110.0, 4.0),
            self.tick(310, 108.0, 5.0),
        ]
        for tick in ticks:
            aggregator.add(tick, computed_at=self.computed_at)
        aggregator.add(self.tick(20, 98.0, 3.0, received_offset=9), computed_at=self.computed_at)

        one_minute = aggregator.bars("VOD.L", "1m")
        self.assertEqual(len(one_minute), 3)
        self.assertEqual(
            (one_minute[0].open, one_minute[0].high, one_minute[0].low, one_minute[0].close, one_minute[0].volume),
            (100.0, 105.0, 98.0, 105.0, 6.0),
        )

        five_minute = aggregator.bars("VOD.L", "5m")
        self.assertEqual(len(five_minute), 2)
        self.assertEqual(
            (five_minute[0].open, five_minute[0].high, five_minute[0].low, five_minute[0].close, five_minute[0].volume),
            (100.0, 110.0, 98.0, 110.0, 10.0),
        )
        self.assertEqual(five_minute[0].market_asof, ticks[3].market_asof)
        self.assertEqual(five_minute[0].computed_at, self.computed_at)

    def test_utc_timestamps_are_required(self):
        with self.assertRaises(ValueError):
            Tick(
                instrument_id="VOD.L",
                price=100.0,
                size=1.0,
                market_asof=datetime(2026, 7, 13, 10, 0),
                received_at=datetime(2026, 7, 13, 10, 0, tzinfo=UTC),
            )

    def test_tick_rejects_market_timestamp_far_after_receipt(self):
        received_at = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
        with self.assertRaisesRegex(ValueError, "market_asof"):
            Tick(
                instrument_id="VOD.L",
                price=100.0,
                size=1.0,
                market_asof=received_at + timedelta(minutes=10),
                received_at=received_at,
            )


class FreshnessAndHorizonTests(MarketRuntimeTestCase):
    def test_freshness_uses_market_timestamp_and_category_threshold(self):
        stock = self.instrument(category="stock")
        crypto = self.instrument(symbol="BTC-USD", category="crypto")
        market_asof = self.computed_at - timedelta(seconds=20)
        thresholds = {
            InstrumentCategory.STOCK: timedelta(seconds=30),
            InstrumentCategory.CRYPTO: timedelta(seconds=10),
        }

        stock_freshness = evaluate_freshness(stock, market_asof, self.computed_at, thresholds)
        crypto_freshness = evaluate_freshness(crypto, market_asof, self.computed_at, thresholds)

        self.assertFalse(stock_freshness.is_stale)
        self.assertTrue(crypto_freshness.is_stale)
        self.assertEqual(stock_freshness.age, timedelta(seconds=20))
        self.assertEqual(stock_freshness.market_asof, market_asof)
        self.assertEqual(stock_freshness.computed_at, self.computed_at)

    def test_future_market_timestamp_is_stale(self):
        stock = self.instrument(category="stock")
        freshness = evaluate_freshness(
            stock,
            self.computed_at + timedelta(minutes=10),
            self.computed_at,
        )

        self.assertTrue(freshness.is_stale)

    def test_horizon_adapts_to_category_activity_session_and_freshness(self):
        stock = self.instrument(category="stock")
        fresh = self.freshness(stock)
        stale = evaluate_freshness(
            stock,
            self.computed_at - timedelta(minutes=5),
            self.computed_at,
            {InstrumentCategory.STOCK: timedelta(seconds=30)},
        )

        self.assertEqual(
            classify_horizon(stock, liquidity=0.9, activity=0.8, volatility=0.02, session_active=True, freshness=fresh),
            Horizon.INTRADAY,
        )
        self.assertEqual(
            classify_horizon(stock, liquidity=0.9, activity=0.8, volatility=0.02, session_active=True, freshness=stale),
            Horizon.SWING,
        )
        self.assertEqual(
            classify_horizon(stock, liquidity=0.9, activity=0.8, volatility=0.02, session_active=False, freshness=fresh),
            Horizon.SWING,
        )
        bond = self.instrument(category="bonds")
        self.assertEqual(
            classify_horizon(bond, liquidity=1.0, activity=1.0, volatility=0.1, session_active=True, freshness=self.freshness(bond)),
            Horizon.SWING,
        )


class DecisionAndRankingTests(MarketRuntimeTestCase):
    def opportunity(self, instrument, score, horizon=Horizon.INTRADAY, actionable=True, freshness=None):
        return Opportunity(
            instrument=instrument,
            horizon=horizon,
            score=score,
            actionable=actionable,
            evidence=(
                OpportunityEvidence(
                    name="momentum",
                    value=score,
                    market_asof=self.computed_at - timedelta(seconds=5),
                ),
            ),
            freshness=freshness or self.freshness(instrument),
            trade_plan=self.plan() if actionable else None,
            computed_at=self.computed_at,
        )

    def test_trade_plan_requires_complete_decision_fields(self):
        with self.assertRaises(TypeError):
            TradePlan(
                side="buy",
                entry_zone=(99.0, 101.0),
                entry_trigger="Break 101",
                invalidation="Close below 98",
                stop=98.0,
                targets=(105.0,),
                trailing_rule=None,
            )
        with self.assertRaises(ValueError):
            TradePlan(
                side="buy",
                entry_zone=(99.0, 101.0),
                entry_trigger="Break 101",
                invalidation="Close below 98",
                stop=98.0,
                targets=(),
                trailing_rule=None,
                time_stop="Session close",
            )
        with self.assertRaises(ValueError):
            Opportunity(
                instrument=self.instrument(),
                horizon=Horizon.INTRADAY,
                score=1.0,
                actionable=True,
                evidence=(),
                freshness=self.freshness(self.instrument()),
                trade_plan=None,
                computed_at=self.computed_at,
            )

    def test_ranking_rejects_context_stale_and_non_actionable_rows(self):
        stock = self.instrument(symbol="VOD.L", category="stock")
        context = self.instrument(symbol="UK10Y", category="bond yields")
        stale = evaluate_freshness(
            stock,
            self.computed_at - timedelta(minutes=5),
            self.computed_at,
            {InstrumentCategory.STOCK: timedelta(seconds=30)},
        )
        rows = [
            self.opportunity(stock, 80.0),
            self.opportunity(context, 100.0),
            self.opportunity(stock, 90.0, freshness=stale),
            self.opportunity(stock, 95.0, actionable=False),
        ]

        ranked = rank_opportunities(rows)

        self.assertEqual([row.opportunity.score for row in ranked], [80.0])
        self.assertEqual(ranked[0].opportunity.instrument.symbol, "VOD.L")

    def test_ranking_normalizes_within_asset_class_and_horizon_cohorts(self):
        rows = [
            self.opportunity(self.instrument(symbol="A.L", category="stock"), 90.0),
            self.opportunity(self.instrument(symbol="B.L", category="stock"), 60.0),
            self.opportunity(self.instrument(symbol="EURGBP", category="fx"), 10.0),
            self.opportunity(self.instrument(symbol="GBPUSD", category="fx"), 9.0),
        ]

        ranked = rank_opportunities(rows)
        by_symbol = {row.opportunity.instrument.symbol: row for row in ranked}

        self.assertEqual(by_symbol["A.L"].cohort_rank, 1)
        self.assertEqual(by_symbol["B.L"].cohort_rank, 2)
        self.assertEqual(by_symbol["EURGBP"].cohort_rank, 1)
        self.assertEqual(by_symbol["GBPUSD"].cohort_rank, 2)
        self.assertEqual(by_symbol["A.L"].cohort_score, 1.0)
        self.assertEqual(by_symbol["B.L"].cohort_score, 0.0)
        self.assertEqual(by_symbol["EURGBP"].cohort_score, 1.0)
        self.assertEqual(by_symbol["GBPUSD"].cohort_score, 0.0)
        self.assertTrue(all(0.0 <= row.priority <= 1.0 for row in ranked))
        self.assertGreater(by_symbol["A.L"].priority, by_symbol["B.L"].priority)
        self.assertGreater(by_symbol["EURGBP"].priority, by_symbol["GBPUSD"].priority)


if __name__ == "__main__":
    unittest.main()
