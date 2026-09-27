import type { Asset } from './api/types'

export const ASSETS: Asset[] = ['BTC', 'ETH', 'SOL', 'SILVER']

interface AssetMeta {
  label: string // what the terminal shows; SILVER trades as XAG
  name: string
  pair: string
  dp: number // price decimals
  tvSymbol: string // TradingView symbol for the live chart
}

export const ASSET_META: Record<Asset, AssetMeta> = {
  BTC: { label: 'BTC', name: 'Bitcoin', pair: 'BTC/USD', dp: 2, tvSymbol: 'BINANCE:BTCUSDT' },
  ETH: { label: 'ETH', name: 'Ether', pair: 'ETH/USD', dp: 2, tvSymbol: 'BINANCE:ETHUSDT' },
  SOL: { label: 'SOL', name: 'Solana', pair: 'SOL/USD', dp: 2, tvSymbol: 'BINANCE:SOLUSDT' },
  SILVER: { label: 'XAG', name: 'Silver', pair: 'XAG/USD', dp: 3, tvSymbol: 'OANDA:XAGUSD' },
}

/** TradingView interval codes offered on the live chart. */
export const TV_INTERVALS = [
  { label: '1H', value: '60' },
  { label: '4H', value: '240' },
  { label: '1D', value: 'D' },
  { label: '1W', value: 'W' },
] as const
export type TvInterval = (typeof TV_INTERVALS)[number]['value']
