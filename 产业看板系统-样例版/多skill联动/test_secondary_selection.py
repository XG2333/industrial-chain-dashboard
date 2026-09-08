# -*- coding: utf-8 -*-
"""二次筛选规则测试：scripts/secondary_selection.py。"""

from secondary_selection import (
    apply_secondary_selection,
    secondary_selection_decision,
)


def _row(title, freq, sector, selected=True):
    return {"title": title, "frequency": freq, "sector": sector, "selected": selected}


def _keep(row):
    keep, _ = secondary_selection_decision(
        row["title"], row["frequency"], row["sector"], row["selected"]
    )
    return keep


def test_not_selected_never_kept():
    row = _row("SMM: 电池级碳酸锂 - 平均价: 日度", "日度", "碳酸锂", selected=False)
    assert not _keep(row)


def test_daily_weekly_kept_for_unspecified_sector():
    assert _keep(_row("SMM: 方形磷酸铁锂电芯（174Ah） - 平均价: 周度", "周度", "电池电芯"))
    assert _keep(_row("SMM: 直流侧储能电池预制舱 - 平均价: 日度", "日度", "储能"))


def test_monthly_and_above_excluded():
    for freq in ("月度", "半月度", "季度", "年度"):
        assert not _keep(_row("SMM: 磷酸铁产量: 月度", freq, "磷化工链")), freq


def test_index_indicators_excluded():
    assert not _keep(_row("SMM: 锂辉石精矿（CIF中国）指数 - 平均价: 日度", "日度", "锂矿"))
    assert not _keep(_row("SMM: 三元前驱体库存指数: 前驱体厂: 周度", "周度", "三元正极"))


def test_inventory_cycle_index_kept_as_inventory_days():
    # "库存周期指数: 分环节库存天数" 是库存天数指标（SMM 命名方式），不算指数
    assert _keep(_row("SMM: 碳酸锂库存周期指数: 分环节库存天数: 总计: 周度", "周度", "碳酸锂"))
    assert _keep(_row("SMM: 碳酸锂库存周期指数: 分环节库存天数: 上游: 周度", "周度", "碳酸锂"))
    # 含"库存周期指数"但无"库存天数"字样同样不算指数
    assert _keep(_row("SMM: 碳酸锂库存周期指数: 总计: 周度", "周度", "碳酸锂"))
    # 纯指数（无库存天数/库存周期指数）仍筛除
    assert not _keep(_row("SMM: 磷酸铁市场流通指数: 月度", "周度", "磷酸铁锂"))


def test_emotion_factor_indicators_excluded():
    assert not _keep(_row("SMM: 磷酸铁出货情绪因子: 上游: 周度", "周度", "磷酸铁锂"))
    assert not _keep(_row("SMM: 磷酸铁成交情绪因子: 总计: 周度", "周度", "磷酸铁锂"))
    assert not _keep(_row("SMM: 磷酸铁购货情绪因子: 下游: 周度", "周度", "磷酸铁锂"))


def test_repair_type_indicators_excluded():
    # 修复型相关指标不保留（即使命中板块保留词）
    assert not _keep(_row("SMM: 修复型磷酸铁锂 - 平均价: 日度", "日度", "磷酸铁锂"))
    assert not _keep(_row("修复型磷酸铁锂(高端款) - 平均价", "日度", "磷酸铁锂"))


def test_lithium_downstream_sectors_fully_excluded():
    for sector in ("负极材料", "隔膜", "辅材", "新能源汽车"):
        assert not _keep(_row("SMM: 干法基膜 - 平均价: 日度", "日度", sector)), sector


def test_lithium_ore_keeps_only_concentrate():
    assert _keep(_row("SMM: 澳大利亚锂辉石精矿（CIF中国）现货 - 平均价: 日度", "日度", "锂矿"))
    assert _keep(_row("SMM: 锂云母精矿（中国现货）（Li₂O: 2.0%-2.5%） - 平均价: 日度", "日度", "锂矿"))
    assert not _keep(_row("SMM: 锂辉石原矿（Li2O: 2%-2.5%，CIF中国) - 平均价: 周度", "周度", "锂矿"))
    # 新规则：指标名称中不带"原矿"的都是精矿——磷锂铝石未写"精矿"但实为精矿，应保留
    assert _keep(_row("SMM: 磷锂铝石（中国现货）（Li₂O: 6%-7%） - 平均价: 日度", "日度", "锂矿"))


def test_phosphorus_chain_keeps_only_iron_phosphate():
    # 磷化工链归入磷酸铁锂板块规则：只保留磷酸铁/磷酸铁锂/磷酸锰铁锂
    assert _keep(_row("SMM: 磷酸铁锂库存: 铁锂厂: 周度", "周度", "磷化工链"))
    assert not _keep(_row("SMM: 热法磷酸成本: 日度", "日度", "磷化工链"))
    assert not _keep(_row("SMM: 磷矿石（云南30%） - 平均价: 日度", "日度", "磷化工链"))
    assert not _keep(_row("SMM: 磷酸 - 平均价: 日度", "日度", "磷化工链"))


def test_lfp_sector_keeps_only_iron_phosphate():
    assert _keep(_row("SMM: 磷酸铁锂加工费: 压实密度≥2.40 g/cm³ - 平均价: 周度", "周度", "磷酸铁锂"))
    assert _keep(_row("SMM: 磷酸铁产量: 月度", "日度", "磷酸铁锂"))
    assert not _keep(_row("SMM: 磷矿石（云南30%） - 平均价: 日度", "日度", "磷酸铁锂"))
    assert not _keep(_row("SMM: 磷酸 - 平均价: 日度", "日度", "磷酸铁锂"))
    # 磷酸锰铁锂（LMFP）属于磷酸铁锂家族，保留
    assert _keep(_row("SMM: 磷酸锰铁锂 - 平均价: 日度", "日度", "磷酸铁锂"))


def test_lfp_specific_compact_density_specs_excluded():
    # 磷酸铁锂板块排除指定压实密度规格（储能型≥2.30g/cm³、动力型≥2.50g/cm³）
    # 的平均价指标（周度版本），其余压实密度规格不受影响
    assert not _keep(_row("SMM: 磷酸铁锂 (储能型压实密度≥2.30g/cm³)-平均价: 周度", "周度", "磷酸铁锂"))
    assert not _keep(_row("SMM: 磷酸铁锂(动力型压实密度≥2.50g/cm³)-平均价: 周度", "周度", "磷酸铁锂"))
    # 同板块其他压实密度规格仍保留
    assert _keep(_row("SMM: 磷酸铁锂(储能型压实密度≥2.40g/cm³)-平均价: 日度", "日度", "磷酸铁锂"))
    assert _keep(_row("SMM: 磷酸铁锂(储能型压实密度≥2.50g/cm³)-平均价: 日度", "日度", "磷酸铁锂"))
    assert _keep(_row("SMM: 磷酸铁锂(粉体压实密度≥2.30g/cm³): 平均价: 日度", "日度", "磷酸铁锂"))
    assert _keep(_row("SMM: 磷酸铁锂加工费: 压实密度≥2.40 g/cm³ - 平均价: 周度", "周度", "磷酸铁锂"))


def test_ternary_sector_keeps_only_precursor_and_material():
    assert _keep(_row("SMM: 5系三元前驱体（单晶/动力型） - 平均价: 日度", "日度", "三元正极"))
    assert _keep(_row("SMM: 8系三元材料（多晶/消费型） - 平均价: 日度", "日度", "三元正极"))
    assert _keep(_row("SMM: 海外三元前驱体产能: 日本: 月度", "日度", "三元正极"))
    assert not _keep(_row("SMM: 三元前驱体库存指数: 前驱体厂: 周度", "周度", "三元正极"))


def test_electrolyte_sector_keeps_only_electrolyte_and_lif6():
    assert _keep(_row("SMM: 电解液（三元动力用）-平均价: 日度", "日度", "电解液产业链"))
    assert _keep(_row("SMM六氟磷酸锂 - 平均价: 日度", "日度", "电解液产业链"))
    assert not _keep(_row("SMM: 碳酸二甲酯DMC (出厂价）- 平均价: 日度", "日度", "电解液产业链"))
    assert not _keep(_row("SMM: 氟代碳酸乙烯酯（FEC）: 平均价: 日度", "日度", "电解液产业链"))


def test_lithium_salt_sector_keeps_only_carbonate_and_hydroxide():
    assert _keep(_row("SMM: 电池级碳酸锂 - 平均价: 日度", "日度", "碳酸锂"))
    assert _keep(_row("SMM: 工业级氢氧化锂 - 平均价: 日度", "日度", "氢氧化锂"))
    assert not _keep(_row("SMM: 电池级无水氯化锂 - 平均价: 日度", "日度", "其他锂盐"))
    assert not _keep(_row("SMM: NMP - 平均价: 日度", "日度", "其他锂盐"))


def test_lithium_salt_keeps_whole_sector_not_title_keyword():
    # 碳酸锂/氢氧化锂板块整板块保留：月差、基差等标题无产品名的指标同样保留
    assert _keep(_row("01-05月差", "日度", "碳酸锂"))
    assert _keep(_row("05-09月差", "日度", "碳酸锂"))
    assert _keep(_row("09-01月差", "日度", "碳酸锂"))
    assert _keep(_row("碳酸锂期现价差: 当月合约: 收盘价: 日度", "日度", "碳酸锂"))
    assert _keep(_row("氢氧化锂粗颗粒-微粉级加工费: 月度", "周度", "氢氧化锂"))
    # 其他锂盐板块整板块筛除（即使标题含"碳酸锂"也不保留）
    assert not _keep(_row("碳酸锂相关: 氯化锂: 平均价: 日度", "日度", "其他锂盐"))


def test_frequency_rule_precedes_sector_rule():
    # 月度数据即使命中板块保留词，也被频率规则筛除
    assert not _keep(_row("SMM: 三元前驱体产能: 月度", "月度", "三元正极"))
    assert not _keep(_row("SMM: 全球硫化锂: 中国产量: 月度", "月度", "其他锂盐"))


def test_batch_apply_fills_fields():
    rows = [
        _row("SMM: 电池级碳酸锂 - 平均价: 日度", "日度", "碳酸锂"),
        _row("SMM: 电池级碳酸锂 - 平均价: 月度", "月度", "碳酸锂", selected=True),
        _row("SMM: 电池级碳酸锂 - 平均价: 日度", "日度", "碳酸锂", selected=False),
    ]
    apply_secondary_selection(rows)
    assert rows[0]["secondary_keep"] is True
    assert rows[1]["secondary_keep"] is False
    assert rows[2]["secondary_keep"] is False
    assert "日度/周度" in rows[1]["secondary_reason"]
    assert "未选中" in rows[2]["secondary_reason"]
