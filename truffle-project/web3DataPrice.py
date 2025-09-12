import json
import time
import math
import os
import pandas as pd
from web3 import Web3, HTTPProvider
import random
# ========================= 实验参数配置 =========================
# 测试场景矩阵
TEST_SCENARIOS = {
    "S1": {"market":"高波动", "quality":"低质量"},
    "S2": {"market":"高波动", "quality":"高质量"},
    "M1": {"market":"供过于求", "quality":"基准质量"},
    "M2": {"market":"供过于求", "quality":"低质量"},
    "L1": {"market":"平衡型", "quality":"高质量"},
    "L2": {"market":"平衡型", "quality":"基准质量"}
}# 市场场景定义
MARKET_SCENARIOS = {
    "高波动": {"D":100, "S":25, "ζ_p":4, "λ_p":1.5, "P̄":100},
    "供过于求": {"D":80, "S":25, "ζ_p":7, "λ_p":0.8, "P̄":100},
    "平衡型": {"D":150, "S":30, "ζ_p":5, "λ_p":0.8, "P̄":100}
}
# 市场场景映射
PERIOD_ENUM_MAP = {"高波动": 0, "供过于求": 1, "平衡型": 2}
# 重复测试次数：1.本研究；2.静态；3.无行为因子
run_counts = {"BASELINE": 2, "STATIC": 1, "NASH": 1}
# 质量配置
QUALITY_PROFILES = {
    "低质量": {"base": {"S_rep":0.7, "S_trans":0.6, "S_comp":0.65, "S_proc":0.6, "S_user":0.55}, "range": 0.15},
    "基准质量": {"base": {"S_rep":0.8, "S_trans":0.8, "S_comp":0.75, "S_proc":0.7, "S_user":0.7}, "range": 0.10},
    "高质量": {"base": {"S_rep":0.9, "S_trans":0.9, "S_comp":0.85, "S_proc":0.8, "S_user":0.85}, "range": 0.05}
}
# 交易者参数范围
TRADER_PARAMS = {
    "seller": {"P_res_s": None, "p0_s": None, "ρ_s": (0.6, 0.9), "λ_cre_s": (0.3, 0.9)},
    "buyer": {"P_res_b": None, "p0_b": None, "ρ_b": (0.4, 0.8), "λ_cre_b": (0.3, 0.9)}
}

# ======================== 链下计算模块 =========================
# 随机质量生成
def generate_quality(quality_type):
    profile = QUALITY_PROFILES[quality_type]
    return {
        k: max(0.1, min(1.0, v * random.uniform(1-profile["range"], 1+profile["range"])))
        for k, v in profile["base"].items()
    }
# 随机交易者生成
def generate_trader_params(role, market_scenario=None, P_off=None):
    """生成随机交易者参数（确保保留价/期望价关系）"""
    ranges = TRADER_PARAMS[role]
    if role == "seller":
        # 基于参考价生成保留价
        P_res_s = P_off * random.uniform(0.5, 1.05)      
        # 市场场景调整
        if market_scenario == "供过于求":P_res_s *= 0.9
        elif market_scenario == "高波动":P_res_s *= 1.1   
        # 确保卖家的初始报价高于保留价
        p0_s = P_res_s * random.uniform(1.05, 1.7)
        return {
            "P_res_s": P_res_s,
            "p0_s": p0_s,
            "ρ_s": random.uniform(*ranges["ρ_s"]),
            "λ_cre_s": random.uniform(*ranges["λ_cre_s"])
        }
    
    else:  # buyer
        # 调整保留价范围
        P_res_b = P_off * random.uniform(0.95, 1.5)
        if market_scenario == "供过于求":
            P_res_b *= 0.9
        elif market_scenario == "高波动":
            P_res_b *= 1.1
            
        # 确保买家的初始报价低于保留价
        p0_b = P_res_b * random.uniform(0.3, 0.95)
        
        return {
            "P_res_b": P_res_b,
            "p0_b": p0_b,
            "ρ_b": random.uniform(*ranges["ρ_b"]),
            "λ_cre_b": random.uniform(*ranges["λ_cre_b"]),
            "Q_re": 0.3
        }

def calculate_offchain_params(scenario, quality_params):
    """计算完整的链下定价参数"""
    # 获取市场参数
    market = MARKET_SCENARIOS[scenario["market"]]
    # 1. 计算市场因子 M_d
    base_d = market["D"]
    if scenario["market"] == "高波动":
        perturbation = random.uniform(-0.10, 0.10)
    else:  # 平衡型 | 供过于求
        perturbation = random.uniform(-0.05, 0.05)
    adjusted_d = base_d * (1 + perturbation)
    supply_ratio = adjusted_d / (market["ζ_p"] * market["S"])
    S_scar = math.log(math.e - 1 + supply_ratio)  # 稀缺性因子
    M_d = market["λ_p"] * market["P̄"] * S_scar
    
    # 2. 计算质量因子 Q_p (使用乘法权重公式)
    # 获取权重 (固定等权重 w_i=0.2)
    weights = [0.2, 0.2, 0.2, 0.2, 0.2]
    
    # 提取质量指标
    S_rep = quality_params["S_rep"]
    S_trans = quality_params["S_trans"]
    S_comp = quality_params["S_comp"]
    S_proc = quality_params["S_proc"]
    S_user = quality_params["S_user"]
    
    # 计算 Q_p = ∏(S_i^w_i)
    Q_p = (
        S_rep ** weights[0] *
        S_trans ** weights[1] *
        S_comp ** weights[2] *
        S_proc ** weights[3] *
        S_user ** weights[4]
    )
    
    # 3. 计算参考价格基准 P_off
    P_off = M_d * Q_p
    
    return {
        "M_d": M_d,
        "Q_p": Q_p,
        "P_off": P_off
    }
# ===================== 智能合约交互模块 =======================
class ContractRunner:
    def __init__(self, contract_address, abi_path, ganache_url):
        # 连接Ganache本地链
        self.w3 = Web3(HTTPProvider(ganache_url)) 
        # 检查连接
        if not self.w3.is_connected():
            raise ConnectionError("无法连接到Ganache节点")       
        # 设置默认账户
        self.account = self.w3.eth.accounts[2] # 使用第3个解锁账户   
        # 加载合约ABI
        with open(abi_path, 'r', encoding='utf-8') as file:
            contract_data = json.load(file)
        abi = contract_data['abi']
        self.contract = self.w3.eth.contract(address=contract_address, abi=abi)
        # 实验数据收集器
        self.results = []
    
    def _send_transaction(self, func, *args, **kwargs):
        """发送交易并等待收据"""
        txn = func(*args, **kwargs).build_transaction({
            'from': self.account,
            'nonce': self.w3.eth.get_transaction_count(self.account),
            'gas': 8000000,  # 足够大的gas限制
            'gasPrice': self.w3.to_wei('10', 'gwei')
        })
        # Ganache特有：直接发送未签名交易
        try:
            tx_hash = self.w3.eth.send_transaction(txn)
            return self.w3.eth.wait_for_transaction_receipt(tx_hash)
        except Exception as e:
            if "exceeds block gas limit" in str(e):
                txn['gas'] = 3000000
                tx_hash = self.w3.eth.send_transaction(txn)
                return self.w3.eth.wait_for_transaction_receipt(tx_hash)
            raise   

    def set_mode(self, mode_name):
        """设置合约定价模式"""
        mode_map = {"BASELINE": 0, "STATIC": 1, "NASH": 2}
        self._send_transaction(
            self.contract.functions.setPricingMode,
            mode_map[mode_name]
        ) 

    def add_product(self, product_id, P_off, Q_p, period_enum):
        """添加产品数据到链上"""
        tx_receipt = self._send_transaction(
            self.contract.functions.addProduct,
            product_id,
            int(P_off),
            int(Q_p),
            period_enum
        )
        return tx_receipt
    
    def add_seller(self, seller_id, params, product_id):
        """添加卖家（使用随机参数）"""
        tx_receipt = self._send_transaction(
            self.contract.functions.addSeller,
            seller_id,
            int(params["P_res_s"] * 10000),
            int(params["p0_s"] * 10000),
            int(params["ρ_s"] * 10000),
            int(params["λ_cre_s"] * 10000),
            product_id,
            5  # N_limit
        )
        return tx_receipt
    
    def add_buyer(self, buyer_id, params):
        """添加买家（使用随机参数）"""
        tx_receipt = self._send_transaction(
            self.contract.functions.addBuyer,
            buyer_id,
            int(params["P_res_b"] * 10000),
            int(params["p0_b"] * 10000),
            int(params["ρ_b"] * 10000),
            int(params["λ_cre_b"] * 10000),
            int(params.get("Q_re", 0.3) * 10000)  # 默认质量阈值
        )
        return tx_receipt
    
    def reset_contract(self):   
        """调用合约的resetAll方法重置状态"""
        try:
            print("重置合约状态...")
            receipt = self._send_transaction(self.contract.functions.resetAll)
            print(f"重置完成! Gas消耗: {receipt['gasUsed']}")
            return True
        except Exception as e:
            print(f"重置失败: {str(e)}")
            return False
    def reset_matching_state(self, specific_seller=""):
        """调用增强版状态重置函数"""
        try:
            receipt = self._send_transaction(
                self.contract.functions.resetMatchingState,
                specific_seller
            )
            print(f"匹配状态重置成功! Gas used: {receipt['gasUsed']}")
            return True
        except Exception as e:
            print(f"匹配状态重置失败: {str(e)}")
            return False
    def run_matching(self, test_id, repeat_idx, mode, scenario):
        """执行单次匹配测试"""
        # 重置合约状态
        if not self.reset_contract():
            return {
                "test_id": test_id,
                "repeat_idx": repeat_idx,
                "error": "Contract reset failed"
            }
        if not self.reset_matching_state():  # 不传参数 = 全局重置
            return {"error": "Matching state reset failed"}
        # 设置实验种子
        deterministic_seed = hash((test_id, mode, repeat_idx)) % (2**32)
        random.seed(deterministic_seed)
        try:
            # 1. 生成随机参数
            quality_params = generate_quality(scenario["quality"])

            # 2. 获取市场类型
            market_scenario=scenario["market"]
            period_enum = PERIOD_ENUM_MAP[scenario["market"]]  

            # 3. 计算链下参数
            start_time = time.time()
            offchain_data = calculate_offchain_params(scenario, quality_params)
            P_off = offchain_data["P_off"]
            Q_p = offchain_data["Q_p"]
            offchain_time = time.time() - start_time

            # 3.5 生成随机交易者参数
            seller_params = generate_trader_params("seller",market_scenario,P_off)
            buyer_params = generate_trader_params("buyer",market_scenario,P_off)

            # 4. 设置定价模式
            self.set_mode(mode)
            
            # 5. 链上添加产品
            product_id = f"{test_id}_{mode}_{repeat_idx}"
            receipt = self.add_product(
                product_id, 
                int(P_off * 10000), 
                int(Q_p * 10000),
                period_enum
            )
            add_product_gas = receipt['gasUsed']
            
            # 6. 链上添加卖家
            seller_id = f"seller_{test_id}_{repeat_idx}"
            receipt = self.add_seller(seller_id, seller_params, product_id)
            add_seller_gas = receipt['gasUsed']
            
            # 7. 链上添加买家
            buyer_id = f"buyer_{test_id}_{repeat_idx}"
            receipt = self.add_buyer(buyer_id, buyer_params)
            add_buyer_gas = receipt['gasUsed']
            
            # 8. 链上执行匹配
            start_match = time.time()
            receipt = self._send_transaction(self.contract.functions.performMatching)
            match_time = time.time() - start_match
            match_gas = receipt['gasUsed']
            
            # 9. 收集链上gas日志
            gas_log = {
                'add_product': add_product_gas,
                'add_seller': add_seller_gas,
                'add_buyer': add_buyer_gas,
                'matching': match_gas
            }
            total_gas = sum(gas_log.values())

            # 10. 结果处理，初始化结果字典
            result = {
                "test_id": test_id,
                "repeat_idx": repeat_idx,
                "mode": mode,
                "scenario": json.dumps(scenario),
                "P_off": round(P_off, 2),
                "P_res_s": seller_params["P_res_s"],
                "P_res_b": buyer_params["P_res_b"],
                "p_0_s":seller_params["p0_s"],
                "p_0_b":buyer_params["p0_b"],
                "offchain_time": round(offchain_time, 4),
                "total_gas": total_gas,
                "match_time": round(match_time, 4),
                "match_success": 0,  # 默认匹配失败
                "failure_reason": "No matching event found",  # 默认失败原因
                "P_on": None,
                "PDR": None,
                "SDF": None,
                "ECE": None,
            }
            
            # 尝试解析匹配事件
            matched_logs = self.contract.events.Matched().process_receipt(receipt)
            matched_detail_logs = self.contract.events.MatchedDetail().process_receipt(receipt)
            
            if matched_logs:
                # 有匹配成功事件
                match_event = matched_logs[0]['args']
                P_on = match_event['price'] / 10000
                P_res_s = seller_params["P_res_s"] / 10000
                P_res_b = buyer_params["P_res_b"] / 10000
                sdf = 1 - abs((P_on - P_res_s) / (P_res_b - P_res_s) - 0.5) if (P_res_b - P_res_s) != 0 else 1.0
                p0_s = seller_params["p0_s"] / 10000
                p0_b = buyer_params["p0_b"] / 10000
                ece = 1 - (abs(p0_s - P_on) + abs(p0_b - P_on))/abs(p0_s - p0_b) if (p0_s - p0_b) != 0 else 1.0
                result.update({
                    "match_success": 1,
                    "P_on": P_on,
                    "PDR": abs(P_on - P_off) / P_off if P_off != 0 else 0,
                    "SDF": sdf,
                    "ECE": ece,
                    "buyer_addr": match_event['buyerId'],
                    "seller_addr": match_event['sellerId'],
                    "failure_reason": ""  
                })
            # 处理详细匹配事件
            elif matched_detail_logs:
                detail_event = matched_detail_logs[0]['args']
                
                # 构建失败原因
                failure_reasons = []
                
                # 1. 质量检查
                if not detail_event['qualityPassed']:
                    failure_reasons.append("质量不满足要求")
                
                # 2. 保留价检查
                if not detail_event['reservePriceValid']:
                    failure_reasons.append("买家保留价低于卖家保留价")
                
                # 3. 价格容错
                if not detail_event['priceRange']:
                    failure_reasons.append("价格超出容错范围")
                
                # 4. 协商失败（当所有前置条件满足但交易失败时）
                if (detail_event['qualityPassed'] and 
                    detail_event['reservePriceValid'] and 
                    not detail_event['dealSuccess']):
                    failure_reasons.append("价格协商失败")
                
                # 组合失败原因
                if failure_reasons:
                    result["failure_reason"] = "; ".join(failure_reasons)
                else:
                    result["failure_reason"] = "未知失败原因"
                
                # 处理交易情况
                if detail_event['dealSuccess']:
                    P_on = detail_event['dealPrice'] / 10000
                    P_res_s = seller_params["P_res_s"] / 10000
                    P_res_b = buyer_params["P_res_b"] / 10000
                    sdf = 1 - abs((P_on - P_res_s) / (P_res_b - P_res_s) - 0.5) if (P_res_b - P_res_s) != 0 else 1.0
                    p0_s = seller_params["p0_s"] / 10000
                    p0_b = buyer_params["p0_b"] / 10000
                    ece = 1 - (abs(p0_s - P_on) + abs(p0_b - P_on))/abs(p0_s - p0_b) if (p0_s - p0_b) != 0 else 1.0
                    result.update({
                        "match_success": 1,
                        "P_on": P_on,
                        "PDR": abs(P_on - P_off) / P_off if P_off != 0 else 0,
                        "SDF": sdf,
                        "ECE": ece,
                        "buyer_addr": detail_event['buyerId'],
                        "seller_addr": detail_event['sellerId']
                    })
            else:
                # 没有匹配事件，但有交易收据
                result["failure_reason"] = "交易成功但未找到匹配事件"
            
            self.results.append(result)
            print(f"Test {test_id}-{repeat_idx} completed. Success: {result['match_success']}")
            return result
            
        except Exception as e:
            match_time = time.time() - start_match
            gas_log['matching'] = 0
            total_gas = sum(gas_log.values())
            
            # 错误处理
            result = {
                "test_id": test_id,
                "repeat_idx": repeat_idx,
                "error": str(e),
                "scenario": json.dumps(scenario),
                "P_off": round(P_off, 2),
                "offchain_time": round(offchain_time, 4),
                "total_gas": total_gas,
                "match_time": round(match_time, 4),
                "match_success": 0,
                "failure_reason": f"Transaction failed: {str(e)}"
            }
            
            self.results.append(result)
            print(f"Test {test_id}-{repeat_idx} failed: {str(e)}")
            # 链下再算一遍

            return result
# ======================== 主实验流程 ========================
if __name__ == "__main__":
    # 配置信息
    CONTRACT_ADDRESS = "0x9303001B46Fd74da139387A746e8bb798e812526"  # 替换为实际合约地址
    ABI_PATH = os.path.join('build', 'contracts', 'DataPrice.json')  # 替换为实际ABI文件路径
    GANACHE_URL = "http://127.0.0.1:7545"  # 默认Ganache URL
    
    # 初始化合约运行器
    try:
        runner = ContractRunner(CONTRACT_ADDRESS, ABI_PATH, GANACHE_URL)
        print(f"Connected to contract at {CONTRACT_ADDRESS}")
        print(f"Block number: {runner.w3.eth.block_number}")
    except Exception as e:
        print(f"初始化失败: {str(e)}")
        exit(1)
    
    # 冒烟测试
    print("\n执行冒烟测试...")
    try:
        # 测试重置功能
        assert runner.reset_contract(), "重置失败"
        assert runner.reset_matching_state(), "匹配状态重置失败"
        print("合约重置测试通过")

        # 设置定价模式  
        runner.set_mode("BASELINE")

        # 测试添加产品
        receipt = runner.add_product("smoke_test", int(100.0 * 10000), int(0.75 * 10000), PERIOD_ENUM_MAP["高波动"] )
        print(f"添加产品成功! Gas used: {receipt['gasUsed']}")
        
        # 测试添加卖家
        seller_params = {
            "P_res_s": 80,
            "p0_s": 100,
            "ρ_s": 0.5,
            "λ_cre_s": 0.7
        }
        receipt = runner.add_seller("seller_smoke", seller_params, "smoke_test")
        print(f"添加卖家成功! Gas used: {receipt['gasUsed']}")
        
        # 测试添加买家
        buyer_params = {
            "P_res_b": 120,
            "p0_b": 90,
            "ρ_b": 0.6,
            "λ_cre_b": 0.8,
            "Q_re": 0.0
        }
        receipt = runner.add_buyer("buyer_smoke", buyer_params)
        print(f"添加买家成功! Gas used: {receipt['gasUsed']}")
        
        # 测试执行匹配
        receipt = runner._send_transaction(runner.contract.functions.performMatching)
        print(f"执行匹配成功! Gas used: {receipt['gasUsed']}")
        
        # 尝试解析事件
        matched_logs = runner.contract.events.Matched().process_receipt(receipt)
        if matched_logs:
            print(f"匹配成功! 价格: {matched_logs[0]['args']['price']/100}")
        else:
            print("未捕获匹配事件，请检查合约事件日志")
        
        print("冒烟测试通过！")
    except Exception as e:
        print(f"冒烟测试失败: {str(e)}")
        exit(1)
    
    # 执行所有测试场景
    all_results = []
    current_test = 0 
    total_tests = sum(run_counts.values()) * 6
   
    print(f"\n开始正式实验，共{total_tests}组测试...")
    
    start_time = time.time()
    # 测试循环
    for test_id, scenario in TEST_SCENARIOS.items():
        for mode, count in run_counts.items():
            for i in range(count):
                # 重置合约状态
                runner.reset_contract()
                
                # 执行匹配测试
                result = runner.run_matching(test_id, i, mode, scenario)
                all_results.append(result)
                 
    # 保存实验结果
    df = pd.DataFrame(all_results)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    results_file = f"output/experiment_results_{timestamp}.csv"
    df.to_csv(results_file, index=False)
    
    # 生成分析报告
    if not df.empty and 'match_success' in df.columns:
        # 场景维度聚合统计（按test_id和mode分组）
        scenario_stats = df.groupby(['test_id', 'mode']).agg({
            'match_success': ['mean', 'count'],
            'PDR': 'mean',
            'SDF':'mean',
            'ECE': 'mean',
            'total_gas': 'mean',
            'match_time': 'mean'
        }).reset_index()   
        # 重命名列（多层索引展平）
        scenario_stats.columns = [
            '场景ID', 
            '定价模式', 
            '平均成功率', 
            '测试次数', 
            '平均价格偏离率', 
            '平均剩余分配公平度',
            '平均期望收敛效率',
            '平均Gas消耗', 
            '平均匹配时间'
        ]
        # 保存场景分析结果
        scenario_file = f"output/scenario_performance_{timestamp}.csv"
        scenario_stats.to_csv(scenario_file, index=False)
        print(f"\n场景分析报告保存至: {scenario_file}")
        print("\n场景性能摘要:")
        print(scenario_stats.round(2))
        # ===========================================
    else:
        print("实验完成，但未收集到有效结果")
    
    total_duration = time.time() - start_time
    print(f"\n总耗时: {total_duration:.2f}秒")