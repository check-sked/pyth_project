# Sources for Analysis 5 and for venue mechanics

Read 2026-11-08/09. Each entry: URL, what it was used for, and the wording relied on.

## Boros (Pendle)

- https://docs.pendle.finance/boros-docs/about-boros/rate-settlement — settlement. "Funding Market, Binance: every 8 hours; Funding Market, Hyperliquid: every 1 hour; Spread Market: the interval of the less frequent leg." Oracle pipeline: "An off-chain bot fetches the actual funding rate from the relevant CEX or perp DEX at each epoch boundary. The rate is submitted to a FundingRateVerifier, validated against one of three independent oracle sources (Chainlink Data Streams, ChaosLabs Risk Oracle, or Pendle's oracle). Once validated, it is forwarded to the FIndex Oracle." "A Spread Market does not have a separate oracle."
- https://docs.pendle.finance/boros-docs/about-boros/market-types — "Funding Markets: the underlying rate is the funding rate of a single perpetual market on a single exchange." "Spread Markets: Rate A − Rate B ... Example BTC Spread HL-Gate."
- https://docs.pendle.finance/boros-docs/about-boros/spread-markets — "In BTC Spread HL-Gate, the market settles every 8 hours. Over each 8-hour window, Hyperliquid's hourly funding prints are averaged and Gate's 8-hour rate is subtracted."
- https://boros-data-dashboard.pendle.finance/markets — live market list with OI and 24h volume per market (JS-rendered; figures quoted in the report were read from the search-engine capture of this page on 2026-11-08, e.g. "#233 BTC Hyperliquid - Gate 18d (27 NOV 26) OI 340 BTC $25.45M, 24h Vol 13.6 BTC $1.02M"; "#232 ETH Hyperliquid - Gate 18d OI 16.79K ETH $35.78M"; "#209 ETH Hyperliquid 18d OI 7.81K ETH $16.65M").
- https://boros-data-dashboard.pendle.finance/funding-rates — per-exchange funding and OI panel. Capture 2026-11-08 shows "NVIDIA · 1 exchanges: Hyperliquid -60.40% ... OI $133.96M", "S&P 500 · 1 exchanges: Hyperliquid", "XYZ100 · 1 exchanges: Hyperliquid"; BTC panel lists Bybit OI $5.22B (not machine-readable, not used for weights).
- https://historical-data.boros.finance/ (index: /files.json) — public archive. `funding-rate/<Exchange>-<Asset>.ndjson.zip` "Historical underlying funding rates sourced from exchanges"; `market-data/<id>-<EXCHANGE>-<SYMBOL>-<MATURITY>/` directories enumerate every Boros market. Used for the Bybit series, Gate/OKX backfill, and the market list.
- https://borosexplorer.com/address/0x0c3bb1eba3b2346aa8ea74720f2d82aa5adedb47 — "Market 233 · BTC spread · Hyperliquid − Gate ... Open interest $21.65M, 24h volume $1.36M" (third-party explorer).
- https://www.kucoin.com/news/flash/pendle-s-boros-hits-10-billion-notional-volume-2-7x-faster-than-pendle-v2 — "on February 5 [2026], Boros ... achieved a milestone of $10 billion in notional trading volume" (BlockBeats via KuCoin).
- https://cryptobriefing.com/boros-launches-funding-rate-spread-markets/ — "Boros ... officially launched its native spread markets on October 15, 2026. The first batch covers ETH and BTC, using funding rates from Hyperliquid and Gate." "By mid-2026, Boros had processed over $20 billion in notional trading volume across more than 170 distinct markets."
- https://www.tokenpost.com/news/investing/32205 — same launch, "settlement occurs every eight hours and uses the average of Hyperliquid's hourly rates since the previous settlement."
- https://www.bitget.com/news/detail/12560605154590 — "Boros has launched the NVDAUSDC-Hyperliquid (USDT collateral) market. This product is the first funding rate market for stock perpetual contracts ... The base annual interest rate for NVDAUSDC is 5.5%, with maturity on February 27, 2026." (Foresight News, 2026-01-15). Plans: "AAPL, TSLA, GOOGL, NASDAQ".
- https://www.linkedin.com/posts/pendlefinance_today-nvidia-funding-market-went-live-on-activity-7417722487448338434-TR4M — Pendle, 2026-01-16: "Today, NVIDIA funding market went live on Boros! ... more RWAs like AAPL, TSLA, GOOGL, NASDAQ".
- https://bex.co/blog/2026/03/11/pendle-v2-boros-multi-chain-defi-fixed-income-layer — third-party: "Pendle is expanding Boros to list equity perpetual assets — S&P 500, NASDAQ, and even single-stock perps like TSLA — building on the existing NVDAUSDC-Hyperliquid pool."
- https://chaoslabs.xyz/posts/defi-rate-swaps-building-risk-infrastructure-for-boros — Chaos Labs post on Boros risk infrastructure; Boros launched on Binance BTC/ETH funding (page mentions Binance).

## Buyers of funding data

- https://docs.ethena.fi/resources/faq — "The protocol-level revenue Ethena generates come from three different sources: 1. Staked ETH yield 2. Perpetual Futures Funding Rates or Expiry Futures Basis 3. Fixed rewards on Liquid Stables." "the mean for annualized open interest-weighted funding rates is 9.03% for ETH and 7.79% for BTC."
- https://docs.ethena.fi/backing-assets/crypto-basis-trade — "For ETH perpetuals ... in 2021 it returned 16%, in 2022 0.6%, in 2023 ~9%, and in 2024 returned ~13% APY on a open interest weighted basis."
- https://docs.ethena.fi/protocol-overview/risks/funding-risk — funding risk and reserve fund.
- Not cited. Ethena's own updates: crypto basis was 1% of USDe backing at end-June 2026 (https://gov.ethenafoundation.com/t/ethena-s-june-2026-governance-update/808) and hedged BTC/ETH was back to 17% by 30 September 2026, with equity perps added (https://gov.ethenafoundation.com/t/ethena-s-july-september-2026-governance-update/857/1). The basis trade is no longer the product, so Ethena is not cited as a buyer of a funding reference.
- https://www.coinglass.com/exchanges/Hyperliquid — CoinGlass publishes a Hyperliquid futures page (DEX coverage). The OI-weighted funding endpoint does not list its constituents: https://docs.coinglass.com/reference/oi-weight-ohlc-history.
- https://fandy.finance/ — Solana funding-rate swap protocol ("swap volatile funding rates for a fixed one, operating in sync with each exchange's settlement cycle").
- https://pindar.finance/ — "the first market for Hyperliquid funding rates" (testnet).
- https://www.clamphyperevm.com/how — HyperEVM funding swap; floating leg recomputed on-chain from HyperCore prices with Hyperliquid's formula.
- https://dappsatlas.com/rankings/category/interest-rate-derivatives — list of on-chain rate derivatives (Boros TVL $7.64M, Rho Protocol, IPOR, Voltz).

## Composite funding publishers

- https://docs.coinglass.com/reference/oi-weight-ohlc-history — "/api/futures/funding-rate/oi-weight-history: open interest-weighted funding rate data in OHLC format". Analytics API (key required).
- https://docs.coinglass.com/reference/vol-weight-ohlc-history — volume-weighted variant.
- https://defirate.com/perps/bitcoin/ — dashboard showing a weighted average BTC funding rate across tracked exchanges (analytics, not a settlement product).
- https://cryptokeyhole.com/charts/btc/?metric=ckh.MktPerpetualFundingRate — dashboard: market-wide weighted BTC perp funding (analytics).
- https://blog.volmex.finance/vpr-indices/ — Volmex page mentioning a "Funding Rate Index" among its indices (index publisher; methodology not retrieved, so not assessed).
- https://docs.cfbenchmarks.com/Perpetual_Funding_Rate_Index_Methodology.pdf — CF Perpetual Funding Rate Index (single venue): "calculated based on all funding rates observed from the designated perpetual contract on the Relevant Exchange within a 24-hour observation window"; example KFRI = Kraken PF_XBTUSD.
- https://docs.cfbenchmarks.com/CF%20Market-Wide%20Perpetual%20Funding%20Rate%20Index.pdf — CF Market-Wide Perpetual Funding Rate Index, Version 1.0 issued 3 Jul 2026. "size- and liquidity-weighted composite of per-exchange funding rate reference rates"; "Constituents: Binance, Bybit, OKX, Gate.io, Crypto.com, Kraken"; "Blend Weight 0.50 (50% volume / 50% open interest)"; "Concentration Cap 30%"; "Exclusion Threshold 3.0 ... Scale Floor 3.0% per year ... Minimum Survivors 3"; "Open interest eligibility floor USD 50 million"; "Calculation frequency: once per Calculation Day ... 8:00 a.m. London"; "Data Source: the published per-exchange perpetual funding rate indices ... no raw funding settlements are read directly". Administrator: "CF Benchmarks is authorised and regulated by the Financial Conduct Authority (FCA) as a Registered Benchmark Administrator (FRN 847100) under the UK Benchmarks Regulation."
- https://www.cfbenchmarks.com/documentation/indices — index documentation list including both funding indices.
- https://docs.chain.link/datalink.md — DataLink data categories include "Perpetual Funding Rates: Periodic payments exchanged between long and short traders in perpetual futures markets". "A key distinction of DataLink compared to Chainlink Data Feeds or Data Streams is its single-source nature ... DataLink feeds provide access to bespoke and proprietary data from one specific provider." "No validation of source data quality" by Chainlink for DataLink feeds.
- https://chain.link/article/onchain-funding-rates — Chainlink article on funding rates (explanatory; no composite funding product named).

## Pyth

- https://docs.pyth.network/pro/symbology-reference — asset types: "funding-rate: Funding rates of perpetual futures on exchanges such as Binance and Deribit"; "interest-rate: Benchmark interest rates such as SOFR, and US Treasury prices and yields"; "crypto-redemption-rate: Real-time swap rates derived from smart contracts for the redemption of liquid staking ... tokens"; field "interval: Funding interval for funding-rate feeds (instrument type rate), e.g. 8h".
- https://docs.pyth.network/api-reference/schemas/instrument-type — "rate: A rate rather than a price, such as a funding rate (FundingRate.Binance.BTC/USDT), a redemption rate or an interest rate."
- https://pyth.dourolabs.app/v1/symbols?asset_type=funding-rate — live catalogue, saved to data/raw/pyth/symbols_funding-rate.json on 2026-11-09: 15 feeds (11 stable: Binance BTC/ETH/SOL 8h, Deribit BTC/ETH/SOL 1h and 8h, Hyperliquid BTC/ETH 1h; 4 coming_soon: Bybit BTC/ETH, OKX BTC/ETH). All `min_publishers` 1 (stable) or 3 (coming soon).
- https://pyth.dourolabs.app/v1/symbols?asset_type=interest-rate — 82 feeds (33 stable), incl. SOFR, EFFR, OBFR, BGCR, TGCR, US Treasury yields US2Y..US30Y and constant-maturity indices `InterestRate.Index.CMUS*`.
- https://www.pyth.network/publishers — publisher list names Binance, OKX and Hyperliquid (read 2026-11-08). Lighter is not listed.
- https://legacy.pyth.network/publishers — lists Bybit ("real-time prices to over 350 spot pairs") and Gate.io ("real-time cryptocurrency data"). Same announcements: https://www.pyth.network/blog/new-pyth-data-provider-bybit and https://www.pyth.network/blog/new-pyth-data-provider-gate-io. These are price publishers, not funding-rate publishers.

## Venue funding mechanics and caps

- https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding — "funding is paid every hour at one eighth of the computed rate"; "Funding on Hyperliquid is capped at 0.5%/hour"; interest rate "0.01% every 8 hours, which is 0.00125% every hour, or 11.6% APR"; HIP-3 "funding rate multiplier and interest rate" set by deployer.
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals — fundingHistory, metaAndAssetCtxs.
- https://docs.lighter.xyz/trading/funding — hourly; "BigClamp limits funding payments to 4% per 8 hours, or 0.5% per hour"; "FundingPremiumMultiplier ... 1 for crypto markets, 1/2 for RWA markets"; "When the funding rate is positive, users with long positions pay".
- https://docs.lighter.xyz/api/funding/fundings — endpoint schema (timestamp, value, rate, direction; 750 rows per call).
- https://www.binance.com/en/support/faq/introduction-to-binance-futures-funding-rates-360033525031 — formula; interest 0.01% per 8h; "Cap = 0.75 × Maintenance Margin Ratio" for ≥30x contracts.
- https://safearbitrage.com/en/blog/funding-rate-cap-and-floor/ — third-party read of /fapi/v1/fundingInfo on 2026-09-27: "BTC and ETH have the narrowest band: ±0.3%".
- https://data.binance.vision/ (S3 listing https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/futures/um/monthly/fundingRate/) — Binance public archive used instead of the geo-blocked REST API; GitHub README at https://github.com/binance/binance-public-data .
- https://www.okx.com/docs-v5/en/ — OKX v5 API reference (funding-rate-history, funding-rate, open-interest, rubik open-interest-history).
- https://www.gate.com/help/futures/futures-logic/27569/funding-rate-and-funding-fee — "Funding Rate = Clamp[(Average Premium Index + Clamp(8-Hour Interest Rate − Average Premium Index, −0.05%, 0.05%)) / (8 / N), −fmax, fmax]"; "The base interest rate for Gate cryptocurrency contracts is 0.03%; the base interest rate for traditional finance contracts is 0."
- https://www.gate.com/announcements/article/46587/gate-perpetual-futures-info-api-add-funding-rate-limit-field — `funding_rate_limit` field.
- https://bybit-exchange.github.io/docs/v5/market/history-fund-rate — Bybit endpoint (geo-blocked from this machine: HTTP 403 CloudFront on api.bybit.com and api.bytick.com, 2026-11-08).
- https://www.bybit.com/en/help-center/article/Introduction-to-Funding-Rate — "Funding Rate Upper Limit = min((Initial Margin Rate - Maintenance Margin Rate) x 0.75, Maintenance Margin Rate) ... Where IMR and MMR represent the initial margin rate and maintenance margin rate requirements of the lowest risk limit tier for each symbol." The per-symbol IMR/MMR tiers come from the (geo-blocked) risk-limit endpoint, so the numeric cap is NOT AVAILABLE here.
