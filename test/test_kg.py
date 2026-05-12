from  logic_layer.kg_service import MedicalKG

kg = MedicalKG()
print(kg.get_drug_info("布洛芬"))
kg.close()
