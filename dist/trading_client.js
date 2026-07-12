const axios = require('axios');

/**
 * Trading Algo Client - Simple wrapper for frontend integration
 */
class TradingSignalClient {
  constructor(baseURL = 'http://localhost:5000') {
    this.baseURL = baseURL;
  }

  async getSignal(symbol) {
    try {
      const res = await axios.get(`${this.baseURL}/signal/${symbol}`);
      return res.data;
    } catch (error) {
      return { error: error.message };
    }
  }

  async scan() {
    try {
      const res = await axios.get(`${this.baseURL}/scan`);
      return res.data;
    } catch (error) {
      return { error: error.message };
    }
  }

  getTradeRecommendation(signal) {
    if (!signal.go_long || signal.vol_z < 1.5) {
      return null;
    }
    
    const leverage = signal.signal_strength;
    const contracts = Math.floor(1000 / 150); // ~$150 per contract
    
    return {
      action: 'BUY_BULL_CALL_SPREAD',
      symbol: signal.symbol,
      leverage: leverage,
      contracts: Math.min(contracts, 3),
      price: signal.price,
      confidence: signal.confidence,
      vol_z: signal.vol_z
    };
  }
}

module.exports = TradingSignalClient;

// Usage:
// const client = new TradingSignalClient();
// const signal = await client.getSignal('IONQ.US');
// const trade = client.getTradeRecommendation(signal);