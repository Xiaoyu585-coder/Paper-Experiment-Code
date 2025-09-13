// SPDX-License-Identifier: GPL-3.0
pragma solidity ^0.8.0;
contract DataPrice {
    struct Buyer {
        string id; // Buyer ID
        uint256 reservePrice; // Reserve price(P_res)
        uint256 initialPrice; // Initial quote(p_0)
        uint256 trust; // Platform trust index(λ_cre)
        uint256 lossAversion; // Loss aversion index(ρ)
        uint256 qualityRequest;// Quality acceptance threshold(Q_re)
    }
    struct Seller {
        string id; // Seller ID
        uint256 reservePrice; // Reserve price(P_res)
        uint256 initialPrice; // Initial quote(p_0)
        uint256 trust; // Platform trust index(λ_cre)
        uint256 lossAversion; // Loss aversion index(ρ)
        string productId; // Product ID
        uint256 firstBid; 
        uint256 matchCount; 
        uint256 maxMatchCount; 
    }
    // Market period enumeration
    enum MarketPeriod {HIGH_VOLATILITY, SUPPLY_SURPLUS, BALANCE}
    struct Product {
        string productId; // Product ID
        uint256 benchmarkPrice; // Benchmark price(P_off)
        uint256 qualityFactor; // Data quality(Q_p)
        MarketPeriod period;  // Mark market period
    }
    // Interactive structure, reduce parameter transmission
    struct NegotiationContext {
        uint256 benchmarkPrice;
        uint256 qualityFactor;
        uint256 buyerFirstOffer;
        uint256 adjustedSellerFirstBid; // Adjusted quote(p_1)
        uint256 diff;
        uint256 buyerMinProfit;
        uint256 sellerMinProfit;
        uint256 buyerBehavioral;
        uint256 sellerBehavioral;
    }
    Buyer[] public buyers; // All buyers
    Seller[] public sellers; // All sellers
    Product[] public products; // All product
    // Batch processing of status variables
    uint256 public currentBuyerBatch = 0;
    uint256 public batchSize = 1; // The number of buyers processed in each batch can be adjusted as needed.

    event BatchProcessed(uint256 batchIndex, uint256 processedCount);
    event BuyerAdded(string id, uint256 reservePrice, uint256 initialPrice, uint256 trust, uint256 lossAversion, uint256 qualityRequest);
    event SellerAdded(string id, uint256 reservePrice, uint256 initialPrice, uint256 trust, uint256 lossAversion, string productId, uint256 maxMatchCount);
    event ProductAdded(string productId, uint256 benchmarkPrice, uint256 qualityFactor);
    event Matched(string buyerId, string sellerId, uint256 price);
    event SellerMaxMatchesReached(string sellerId); 
    event MatchedDetail(
        string indexed buyerId,
        string indexed sellerId,
        bool qualityPassed,       // Does the product quality meet the buyer's threshold?
        bool reservePriceValid,   // Is the buyer's reserve price higher than the seller's?
        bool priceRange,          // Is the reference price within the acceptable range for the traders?
        bool dealSuccess,         // Was the match successful?
        uint256 dealPrice,        // The matching price when the match is successful
        string productId,         // The matched product ID
        uint256 benchmarkPrice    // 
    );
    // function getBuyersCount() public view returns (uint256) {
    //     return buyers.length;
    // }
    // function getSellersCount() public view returns (uint256) {
    //     return sellers.length;
    // }
    // function getProductsCount() public view returns (uint256) {
    //     return products.length;
    // }
    // Initialization
    function resetAll() public {
        delete buyers;
        delete sellers;
        delete products;
    }
    // Pricing model enumeration
    enum PricingMode { BASELINE, STATIC, NASH }
    PricingMode public currentMode = PricingMode.BASELINE;

    function setPricingMode(uint _mode) external {
        require(_mode <= uint(PricingMode.NASH), "Invalid mode");
        currentMode = PricingMode(_mode);
    }
    // Add product data
    function addProduct(string memory productId, uint256 benchmarkPrice, uint256 qualityFactor,  MarketPeriod period) public {
        products.push(Product({productId: productId, benchmarkPrice: benchmarkPrice, qualityFactor: qualityFactor, period: period}));
        emit ProductAdded(productId, benchmarkPrice, qualityFactor);
    }
    // Add buyer data
    function addBuyer(string memory id, uint256 reservePrice, uint256 initialPrice, uint256 trust, uint256 lossAversion, uint256 qualityRequest) public {
        require(reservePrice > 0 && initialPrice > 0, "Prices must be positive");
        buyers.push(Buyer({id: id, reservePrice: reservePrice, initialPrice: initialPrice, trust: trust, lossAversion: lossAversion, qualityRequest: qualityRequest}));
        emit BuyerAdded(id, reservePrice, initialPrice, trust, lossAversion, qualityRequest);
    }
    // Add seller data
    function addSeller(string memory id, uint256 reservePrice, uint256 initialPrice, 
                      uint256 trust, uint256 lossAversion, string memory productId,
                      uint256 maxMatchCount) public {
        require(reservePrice > 0 && initialPrice > 0, "Prices must be positive");
        uint256 benchmarkPrice = getBenchmark(productId);
        require(benchmarkPrice > 0, "Product not found");
        uint256 computedPrice = calculateSellerPrice(initialPrice, benchmarkPrice, trust);        
        sellers.push(Seller({
            id: id,
            reservePrice: reservePrice,
            initialPrice: initialPrice,
            trust: trust,
            lossAversion: lossAversion,
            productId: productId,
            firstBid: computedPrice,
            matchCount: 0,
            maxMatchCount: maxMatchCount
        }));        
        emit SellerAdded(id, reservePrice, initialPrice, trust, lossAversion, productId, maxMatchCount);
    }    
    // Obtain the number of times the seller was matched
    function getSellerMatchCount(string memory sellerId) public view returns (uint256) {
        for (uint256 i = 0; i < sellers.length; i++) {
            if (compareStrings(sellers[i].id, sellerId)) {
                return sellers[i].matchCount;
            }
        }
        revert("Seller not found");
    }    
    // Obtain all the information of the sellers
    function getAllSellers() public view returns (Seller[] memory) {
        return sellers;
    }
    // Obtain the seller index
    function getSellerIndex(string memory sellerId) internal view returns (int256) {
        for (uint256 i = 0; i < sellers.length; i++) {
            if (compareStrings(sellers[i].id, sellerId)) {
                return int256(i);
            }
        }
        return -1;
    }    
    // Status reset
    function resetMatchingState(string memory specificSeller) public {
        // Reset batch index
        currentBuyerBatch = 0;
        
        if(bytes(specificSeller).length == 0) {
            // Global Reset Mode: Reset all sellers
            for(uint i = 0; i < sellers.length; i++) {
                sellers[i].matchCount = 0;
            }
        } else {
            // Specify the seller to reset the mode
            int256 index = getSellerIndex(specificSeller);
            if(index >= 0) {
                sellers[uint256(index)].matchCount = 0;
            }
        }
    }
    // Obtain the benchmark price of the product
    function getBenchmark(string memory productId) internal view returns (uint256) {
        for (uint256 i = 0; i < products.length; i++) {
            if (compareStrings(products[i].productId, productId)) {
                return (products[i].benchmarkPrice);
            }
        }
        return 0;
    }
    // Obtain the benchmark price of the product
    function getProduct(string memory productId) internal view returns (uint256, uint256) {
        for (uint256 i = 0; i < products.length; i++) {
            if (compareStrings(products[i].productId, productId)) {
                return (products[i].benchmarkPrice, products[i].qualityFactor);
            }
        }
        return (0,0);
    }
    // Compare strings
    function compareStrings(string memory a, string memory b) internal pure returns (bool) {
        return keccak256(bytes(a)) == keccak256(bytes(b));
    }
    // Process buyers in batches
    function performMatching() public returns (bool) {
        uint256 startIndex = currentBuyerBatch * batchSize;
        uint256 endIndex = (currentBuyerBatch + 1) * batchSize; 
        // Prevent going beyond the array boundaries
        if (endIndex > buyers.length) {
            endIndex = buyers.length;
        }
        // If there are no batches to process, reset and return.
        if (startIndex >= endIndex) {
            currentBuyerBatch = 0;
            return false; // Indicates processing completion
        }
        uint256 processedCount = 0;     
        // Handle the buyers of the current batch
        for (uint256 i = startIndex; i < endIndex; i++) {
            _processSingleBuyer(i);
            processedCount++;
        }
        // Update batch index
        currentBuyerBatch++;   

        emit BatchProcessed(currentBuyerBatch - 1, processedCount);
        return true; // Indicating that there are still more batches that need to be processed
    }
    //Single batch processing of buyers
    function _processSingleBuyer(uint256 buyerIndex) internal {
        Buyer storage buyer = buyers[buyerIndex];
        string memory bestSellerId = "";
        uint256 bestMatchPrice = type(uint256).max;
        uint256 bestSellerIndex = type(uint256).max;
        
        // Traverse the sellers
        for (uint256 j = 0; j < sellers.length; j++) {
            // Check whether the seller has reached the maximum matching limit.
            if (sellers[j].matchCount >= sellers[j].maxMatchCount) {
                continue;
            }
            (uint256 benchmarkPrice, uint256 qualityFactor) = getProduct(sellers[j].productId);    
            // Create a context object
            NegotiationContext memory context = NegotiationContext({
                benchmarkPrice: benchmarkPrice,
                qualityFactor: qualityFactor,
                buyerFirstOffer: 0,
                adjustedSellerFirstBid: 0,
                diff: 0,
                buyerMinProfit: 0,
                sellerMinProfit: 0,
                buyerBehavioral: 0,
                sellerBehavioral: 0
            });
            
            // Calculate the matching results
            uint256 matchPrice = _calculateMatch(buyer, sellers[j], context);
            // Record the matching details into the event.
            emit MatchedDetail(
                buyer.id,
                sellers[j].id,
                context.qualityFactor > buyer.qualityRequest, //qualityPassed
                buyer.reservePrice > sellers[j].reservePrice,   //  reserveValid
                //priceRange
                (matchPrice > sellers[j].reservePrice - sellers[j].reservePrice * sellers[j].lossAversion/50000) 
                && (matchPrice < buyer.reservePrice + buyer.reservePrice * buyer.lossAversion/50000),
                matchPrice > 0,                              // dealSuccess
                matchPrice,                                  // dealPrice
                sellers[j].productId,                        // productId
                context.benchmarkPrice                       // benchmarkPrice
            );
            
            // Update the best match
            if (matchPrice > 0 && matchPrice < bestMatchPrice) {
                bestMatchPrice = matchPrice;
                bestSellerId = sellers[j].id;
                bestSellerIndex = j;
            }
        }
        
        // Trigger the matching event and update the number of times the seller has been matched.
        if (bestMatchPrice != type(uint256).max) {
            emit Matched(buyer.id, bestSellerId, bestMatchPrice);
            sellers[bestSellerIndex].matchCount++;
            
            if (sellers[bestSellerIndex].matchCount >= sellers[bestSellerIndex].maxMatchCount) {
                emit SellerMaxMatchesReached(bestSellerId);
            }
        }
    }
    //The internal calculation of the perfomMatching function
    // Verification Phase
    function _calculateMatch(Buyer storage buyer, Seller storage seller, NegotiationContext memory context) internal view returns (uint256) {
        // Quality verification and reserve price verification
        if (!_validatePreConditions(context.qualityFactor, buyer.qualityRequest, seller.reservePrice, buyer.reservePrice)) {
            return 0; // Early termination
        }
        // Mode branching calculation of candidate prices
        uint256 candidatePrice = _calculateCandidatePrice(buyer, seller, context);
        // Price range and satisfaction threshold verification
        return _validatePostConditions(candidatePrice, seller.reservePrice, buyer.reservePrice, seller.lossAversion, buyer.lossAversion) ? candidatePrice : 0;
    }

    // Auxiliary function: Precondition verification (quality + reserve price)
    function _validatePreConditions(
        uint256 qualityFactor,
        uint256 buyerQualityReq,
        uint256 sellerReserve,
        uint256 buyerReserve
    ) private pure returns (bool) {
        // Quality verification (Q_p > Q_re)
        if (qualityFactor <= buyerQualityReq) {
            return false;
        }
        // Verification of reserve price (P_res^b > P_res^s)
        if (buyerReserve <= sellerReserve) {
            return false;
        }
        return true;
    }

    // Auxiliary function: Candidate price calculation (mode branching)
    function _calculateCandidatePrice(
        Buyer storage buyer,
        Seller storage seller,
        NegotiationContext memory context
    ) private view returns (uint256) {
        if (currentMode == PricingMode.STATIC) {
            return context.benchmarkPrice;
        } else if (currentMode == PricingMode.NASH) {
            return (seller.reservePrice + buyer.reservePrice) / 2;
        } else if (currentMode == PricingMode.BASELINE) {
            // Calculate the buyer's initial offer
            context.buyerFirstOffer = calculateBuyerPrice(buyer.initialPrice, context.benchmarkPrice, buyer.trust);
            // Boundary protection
            context.adjustedSellerFirstBid = boundValue(seller.firstBid, seller.reservePrice, buyer.reservePrice);
            context.buyerFirstOffer = boundValue(context.buyerFirstOffer, seller.reservePrice, buyer.reservePrice);
            // Boundary scope
            context.diff = abs(uint256(buyer.reservePrice), uint256(seller.reservePrice));
            // Direct matching check
            if (context.adjustedSellerFirstBid <= context.buyerFirstOffer) {
                return (context.adjustedSellerFirstBid + context.buyerFirstOffer) / 2;
            }
            // Calculate the equilibrium price
            return calculateEquilibriumPrice(
                context.buyerFirstOffer,
                context.adjustedSellerFirstBid,
                calculateBehavioralCoefficient(buyer.reservePrice, context.buyerFirstOffer, buyer.lossAversion, context.diff),
                calculateBehavioralCoefficient(seller.reservePrice, context.adjustedSellerFirstBid, seller.lossAversion, context.diff)
            );
        }
        return 0;
    }
    // Auxiliary function: Postcondition verification (price range + meets threshold)
    function _validatePostConditions(
        uint256 candidatePrice,
        uint256 sellerReserve,
        uint256 buyerReserve,
        uint256 sellerlossAversion,
        uint256 buyerlossAversion
    ) private pure returns (bool) {
        // Price range verification
        if (candidatePrice <= sellerReserve - sellerReserve* sellerlossAversion/50000 || candidatePrice >= buyerReserve + buyerReserve* buyerlossAversion/50000) {
            return false;
        }
        return true;
    }
    // Auxiliary function: Boundary protection
    function boundValue(
        uint256 value,
        uint256 minBound,
        uint256 maxBound
    ) private pure returns (uint256) {
        if (value < minBound) return minBound + (maxBound - minBound)/10;
        if (value > maxBound) return maxBound - (maxBound - minBound)/10;
        return value;
    }
    // Auxiliary: Calculate the buyer's offer price
    function calculateBuyerPrice(uint256 initialPrice, uint256 benchmarkPrice, uint256 trust) internal pure returns (uint256) {
        if (benchmarkPrice >= initialPrice) {
            return initialPrice + (trust * (benchmarkPrice - initialPrice)) / 10000;
        } else {
            return initialPrice - (trust * (initialPrice - benchmarkPrice)) / 10000;
        }
    }
    // Auxiliary: Calculate the seller's bid
    function calculateSellerPrice(uint256 initialPrice, uint256 benchmarkPrice, uint256 trust) internal pure returns (uint256) {
        if (benchmarkPrice >= initialPrice) {
            return initialPrice + (trust * (benchmarkPrice - initialPrice)) / 10000;
        } else {
            return initialPrice - (trust * (initialPrice - benchmarkPrice)) / 10000;
        }
    }
    // Auxiliary: Calculate Behavioral Adjustment Factor
    function calculateBehavioralCoefficient(uint256 reservePrice, uint256 firstPrice, uint256 lossAversion, uint256 diff) internal pure returns (uint256) {
        uint256 priceDiff = abs(uint256(reservePrice), uint256(firstPrice));
        uint256 denominator = priceDiff + diff;
        if (denominator == 0) {
            return 1; // Extremely un-deviated situation
        }
        return lossAversion * diff / denominator;
    }
    // Auxiliary: Calculate the equilibrium price
    function calculateEquilibriumPrice(uint256 buyerFirstOffer, uint256 sellerFirstBid, uint256 buyerBehavioral, uint256 sellerBehavioral) internal pure returns (uint256) {
        // Auxiliary: Add minimum coefficient protection
        if (buyerBehavioral < 1) buyerBehavioral = 1; // 1% minimum value
        if (sellerBehavioral < 1) sellerBehavioral = 1;

        uint256 priceDiff = sellerFirstBid - buyerFirstOffer;
        uint256 numerator = priceDiff * (10000 - buyerBehavioral) * 10000;
        uint256 denominator = 100000000 - (buyerBehavioral * sellerBehavioral);
        if (denominator <= 0) {
            return 1;
            }
        uint256 adjustment = numerator / denominator;
        return buyerFirstOffer + adjustment;
    }
    // Auxiliary: Calculate the absolute value
    function abs(uint256 a, uint256 b) internal pure returns (uint256) {
        if (a >= b){
            return uint256(a - b);
        }
        else {
            return uint256(b - a);
        }
    }

}
