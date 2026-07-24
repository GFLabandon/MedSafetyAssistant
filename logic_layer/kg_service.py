# logic_layer/kg_service.py
import logging

from neo4j import GraphDatabase
from config import Config


logger = logging.getLogger(__name__)


class MedicalKG:
    def __init__(self):
        self.available = False
        try:
            self.driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
                connection_timeout=Config.NEO4J_CONNECTION_TIMEOUT_SECONDS,
                connection_acquisition_timeout=Config.NEO4J_CONNECTION_TIMEOUT_SECONDS,
            )
            self.available = True
        except Exception:
            logger.warning("neo4j driver initialization failed", exc_info=True)
            self.driver = None

    def close(self):
        if self.driver:
            self.driver.close()
        self.driver = None
        self.available = False

    def _mark_unavailable(self, exc):
        self.available = False
        logger.warning("legacy neo4j query unavailable (%s)", type(exc).__name__)

    def _usable(self):
        return bool(self.driver) and getattr(self, "available", True)

    def get_drug_info(self, drug_names):
        if not self._usable() or not drug_names:
            return []

        info_list = []
        # --- 核心修复：同时查找 Drug 节点和 Ingredient 节点 ---
        query = """
            UNWIND $names AS n
            MATCH (node)
            WHERE (node:Drug AND node.name = n) OR (node:Ingredient AND node.name = n)

            // 能够同时返回药品自身信息，或者成分所属的药品信息
            OPTIONAL MATCH (node)-[:CONTAINS_INGREDIENT]->(i:Ingredient)

            RETURN 
                labels(node) as labels,
                node.name as name, 
                node.dosage as dosage, 
                node.category as category, 
                node.function as function,
                node.desc as desc,
                collect(i.name) as ingredients
            """
        try:
            with self.driver.session() as session:
                result = session.run(query, names=drug_names)
                for record in result:
                    # 兼容处理：如果是 Ingredient 节点，desc 字段就是功能；如果是 Drug，function 是功能
                    is_drug = "Drug" in record['labels']

                    info = {
                        "drug": record['name'],
                        "category": record['category'] if is_drug else "药物成分",
                        "function": record['function'] if is_drug else record['desc'],  # 成分节点用 desc
                        "dosage": record['dosage'] if is_drug else "作为成分存在，请参考具体药物说明",
                        "ingredients": ", ".join(record['ingredients']) if is_drug else record['name']
                    }
                    info_list.append(info)
        except Exception as exc:
            self._mark_unavailable(exc)
            return []
        return info_list

    def check_safety(self, drug_names, user_conditions):
        if not self._usable() or not drug_names:
            return []

        risks = []
        try:
            with self.driver.session() as session:
                # 1.【成分重复检测】 (Duplicate Therapy)
                # 逻辑：比如“泰诺”和“感康”都含有“对乙酰氨基酚”，一起吃会肝衰竭。
                if len(drug_names) > 1:
                    query_dup = """
                    UNWIND $drugs AS d_name
                    MATCH (d:Drug {name: d_name})-[:CONTAINS_INGREDIENT]->(i:Ingredient)
                    WITH i, collect(d.name) as drugs_with_ing
                    WHERE size(drugs_with_ing) > 1
                    RETURN i.name as ingredient, drugs_with_ing
                    """
                    result = session.run(query_dup, drugs=drug_names)
                    for record in result:
                        risks.append({
                            "type": "DUPLICATE_THERAPY",
                            "drug": " + ".join(record['drugs_with_ing']),
                            "condition": "药物过量",
                            "ingredient": record['ingredient'],
                            "reason": f"均含有成分【{record['ingredient']}】，叠加服用会导致肝肾损伤！",
                            "severity": "FATAL"  # 提高为最高警报
                        })

                # 2.【特定状态禁忌】 (Contraindication)
                # 逻辑：吃了头孢喝酒。
                if user_conditions:
                    query_contra = """
                    UNWIND $drugs AS d_name
                    MATCH (d:Drug {name: d_name})-[:CONTAINS_INGREDIENT]->(i:Ingredient)
                    MATCH (i)-[r:CONTRAINDICATED_IN]->(c:Condition)
                    WHERE c.name IN $conditions
                    RETURN d.name as drug, i.name as ingredient, c.name as condition, r.reason as reason, r.severity as severity
                    """
                    result = session.run(query_contra, drugs=drug_names, conditions=user_conditions)
                    for record in result:
                        risks.append({
                            "type": "CONTRAINDICATION",
                            "drug": record['drug'],
                            "condition": record['condition'],
                            "reason": f"成分【{record['ingredient']}】与【{record['condition']}】冲突：{record['reason']}",
                            "severity": record['severity']
                        })

                # 3.【药物相互作用】 (Interaction)
                # 逻辑：布洛芬 + 阿司匹林
                if len(drug_names) > 1:
                    query_ddi = """
                    UNWIND $drugs AS d1_name
                    MATCH (d1:Drug {name: d1_name})-[:CONTAINS_INGREDIENT]->(i1:Ingredient)

                    MATCH (d2:Drug)-[:CONTAINS_INGREDIENT]->(i2:Ingredient)
                    WHERE d2.name IN $drugs AND d1.name <> d2.name

                    MATCH (i1)-[r:INTERACTS_WITH]-(i2)
                    WHERE id(d1) < id(d2) // 去重
                    RETURN d1.name as drug1, d2.name as drug2, r.reason as reason, r.severity as severity
                    """
                    result = session.run(query_ddi, drugs=drug_names)
                    for record in result:
                        risks.append({
                            "type": "INTERACTION",
                            "drug": f"{record['drug1']} + {record['drug2']}",
                            "condition": "药物冲突",
                            "reason": record['reason'],
                            "severity": record['severity']
                        })
        except Exception as exc:
            self._mark_unavailable(exc)
            return []
        return risks
