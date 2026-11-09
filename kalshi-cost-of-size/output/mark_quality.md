790,708 trades, 40 markets, 2026-09-08 -> 2026-11-07
block trades in sample: 0

== A. size concentration (pooled) ==
         trades    contracts  share_trades  share_contracts  cum_share_contracts_from_top
bucket                                                                                   
<100     713403   9333410.07        0.9022           0.1448                        1.0000
100-1k    66139  18114678.22        0.0836           0.2811                        0.8552
1k-5k      9398  17551898.44        0.0119           0.2723                        0.5741
5k-10k     1104   7117932.08        0.0014           0.1104                        0.3018
10k-50k     642  11060282.37        0.0008           0.1716                        0.1913
>=50k        22   1271724.81        0.0000           0.0197                        0.0197

== B. large (>=5k contracts) on-book prints: impact and 30-min reversal ==
n=2063; median |impact| 0.6c; mean 1.0c; share |impact|>=1c 36%; >=3c 7%
of prints that moved >=1c (n=735): median reverted fraction in 30m 0.26; share reverting >=50% 41%

== C. hourly mark dispersion: last trade vs 24h VWAP ==
n hours=56,111; median |last-vwap24| 0.45c; p75 0.94c; p90 1.80c; share >=1c 22%; >=2c 8%; >=5c 1%

== D. staleness at daily 4pm ET snapshot ==
n market-days=2,383; median minutes since last trade 24; share >60m 30%; >6h 7%; >24h 3%
OI-weighted share of market-days with last trade >60m old: 24%

== E. month-end valuation: 2026-09-30 and 2026-10-31 at 4pm ET ==
2026-09-30: markets=40, OI as of date=$56.1M notional; median |last-vwap24h| 0.50c; max 10.4c; sum |last-vwap24h| x OI = $480K; sum (max-min of last/vwap1h/vwap24h) x OI = $521K; markets with last trade >1h old: 30%
2026-10-31: markets=40, OI as of date=$66.8M notional; median |last-vwap24h| 0.46c; max 5.0c; sum |last-vwap24h| x OI = $339K; sum (max-min of last/vwap1h/vwap24h) x OI = $450K; markets with last trade >1h old: 15%
