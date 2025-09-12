# Blockchain Data Pricing Simulation Experiment

This project is a data pricing simulation system based on Ethereum smart contracts, incorporating behavioral economics factors to test and evaluate the performance of various pricing models in simulated market environments.

## Project Overview

The project consists of two core files:
- **`DataPrice.sol`**: Smart contract implementing three data pricing models (BASELINE, STATIC, NASH) and their matching algorithms
- **`web3DataPrice.py`**: Python testing script for interacting with the contract, performing automated tests, and collecting performance metrics

The system simulates data trading processes across different market scenarios (high volatility, supply surplus, balanced) and quality levels (low quality, benchmark quality, high quality), evaluating the performance of various pricing models through quantitative metrics.

## Features

- 🤖 Three pricing algorithm implementations:
  - **BASELINE**: Complex bargaining model based on behavioral economics (core research model)
  - **STATIC**: Static benchmark pricing (simple control group)
  - **NASH**: Nash bargaining solution (theoretical control group)

- 📊 Multi-dimensional performance evaluation metrics:
  - Matching success rate
  - Price Deviation Rate (PDR)
  - Surplus Distribution Fairness (SDF)
  - Expectation Convergence Efficiency (ECE)
  - Gas consumption analysis
  - Execution time analysis

- 🌐 Multiple market scenario simulations:
  - High volatility market
  - Supply surplus market
  - Balanced market

- 🔧 Automated testing framework:
  - Repeatable experiment setup
  - Random parameter generation
  - Detailed result recording
  - CSV report export

## Project Structure

```
├── build/                 # Contract compilation output directory (create manually)
│   └── contracts/
│       └── DataPrice.json # Contract ABI file (compile manually)
├── contracts/
│   └── DataPrice.sol      # Smart contract source code
├── migrations/
│   └── 2_deploy_contracts.js          
├── output/                # Experiment results output directory (created automatically)
│   ├── scenario_performance.csv
│   └── experiment_results.csv
├── web3DataPrice.py       # Testing script
└── README.md              # Project documentation
```

## Installation & Execution

### Prerequisites

1. **Ganache CLI**: Local Ethereum test network
   ```bash
   npm install -g ganache-cli
   ```

2. **Python 3.7+** and required dependencies:
   ```bash
   pip install web3 pandas
   ```

3. **Solidity Compiler** (optional, for recompiling contracts):
   ```bash
   npm install -g solc
   ```

### Deployment & Execution Steps

1. **Start Ganache test network**:
   ```bash
   ganache-cli -p 7545
   ```

2. **Compile and deploy contract** (skip if using existing ABI):
   ```bash
   solcjs --bin --abi DataPrice.sol -o build
   # Use Remix IDE or other tools to deploy contract to Ganache
   ```

3. **Configure contract address**:
   Modify `CONTRACT_ADDRESS` in `web3DataPrice.py` to your deployed contract address:
   ```python
   CONTRACT_ADDRESS = "0xYourContractAddressHere"
   ```

4. **Run test script**:
   ```bash
   python web3DataPrice.py
   ```

5. **View results**:
   After script execution, results will be saved in CSV files in the `output/` directory:
   - `experiment_results_<timestamp>.csv`: Detailed test data
   - `scenario_performance_<timestamp>.csv`: Scenario aggregation analysis

## Contract Functionality

### Pricing Modes

The contract implements three pricing modes, switchable via the `setPricingMode` function:

1. **BASELINE (0)**: Behavioral bargaining model considering trust and loss aversion factors
2. **STATIC (1)**: Static benchmark pricing, directly using market reference price
3. **NASH (2)**: Nash bargaining solution, taking the midpoint of buyer and seller reserve prices

### Core Functions

- `addProduct()`: Add data product information
- `addBuyer()`: Add buyer information
- `addSeller()`: Add seller information
- `performMatching()`: Execute matching algorithm
- `resetAll()`: Reset contract state
- `resetMatchingState()`: Reset matching state

### Event Logging

The contract emits the following events for result tracking:
- `BuyerAdded`: Buyer addition event
- `SellerAdded`: Seller addition event
- `ProductAdded`: Product addition event
- `Matched`: Successful match event
- `MatchedDetail`: Detailed matching result event
- `SellerMaxMatchesReached`: Seller reached maximum matches event

## Test Scenarios

The system tests 6 market and quality combination scenarios:

| Scenario ID | Market Type | Data Quality |
|-------------|-------------|--------------|
| S1          | High Volatility | Low Quality |
| S2          | High Volatility | High Quality |
| M1          | Supply Surplus | Benchmark Quality |
| M2          | Supply Surplus | Low Quality |
| L1          | Balanced        | High Quality |
| L2          | Balanced        | Benchmark Quality |

## Performance Metrics

The test script collects the following performance metrics:

- **Matching Success Rate**: Proportion of successful transactions
- **Price Deviation Rate (PDR)**: Degree of deviation between transaction price and market benchmark price
- **Surplus Distribution Fairness (SDF)**: Fairness of transaction surplus value distribution
- **Expectation Convergence Efficiency (ECE)**: Closeness of transaction price to both parties' initial expectations
- **Gas Consumption**: Blockchain execution cost of contract operations
- **Execution Time**: Off-chain computation and on-chain matching time overhead

## Custom Configuration

You can customize experiment parameters by modifying constants in the script:

- `TEST_SCENARIOS`: Test scenario configuration
- `MARKET_SCENARIOS`: Market parameter settings
- `QUALITY_PROFILES`: Data quality configuration
- `TRADER_PARAMS`: Trader parameter ranges
- `run_counts`: Repeat test counts for each mode

## Troubleshooting

1. **Connection Failed**: Ensure Ganache is running on port 7545
2. **Insufficient Gas**: Increase Gas limit when starting Ganache
3. **Contract Deployment Failed**: Check Solidity version compatibility (requires ≥0.8.0)
4. **Transaction Reverted**: Confirm input parameters meet contract requirements (e.g., positive prices)

## Contributing

Welcome to submit Issues and Pull Requests to improve this project:

1. Fork the project
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.

## References

1. Kahneman, D., & Tversky, A. (1979). Prospect Theory: An Analysis of Decision under Risk.
2. Nash, J. F. (1950). The Bargaining Problem.
3. Smart Contract Development Best Practices - ConsenSys

## Contact

For questions or suggestions, please contact:

- Create a GitHub Issue
- Send email to: [3560054209@qq.com]

---

*Note: This project is for academic research purposes and is not recommended for direct use in production environments.*
