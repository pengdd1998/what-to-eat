-- 0006：图谱补强菜库补种（2026-09-16，food-taxonomy §9 阶段三）
-- 缺口品类：pot-tang（烫煮）/ pot-congee（粥品）/ light-dimsum（点心）此前零存量，
-- 新链节点收口无库可配。补种 9 道（expand-only：纯 INSERT，不动既有行）。

INSERT OR IGNORE INTO dish_library
(dish_slug, dish_name, category, base_score, tags, active) VALUES
-- 烫煮自选 pot-tang
('malatang',        '麻辣烫',       '简餐', 0.72, '["想喝汤","重口味"]',            1),
('maocai',          '冒菜',         '川菜', 0.70, '["想喝汤","重口味"]',            1),
('guandongzhu',     '关东煮',       '夜宵', 0.66, '["想喝汤","想慢享"]',            1),
-- 粥品 pot-congee
('pidanshourouzhou','皮蛋瘦肉粥',   '粤式', 0.74, '["想喝汤","清淡"]',              1),
('shaguozhou',      '砂锅虾粥',     '粤式', 0.70, '["想喝汤","想慢享"]',            1),
('baizhoupeicai',   '白粥配小菜',   '粤式', 0.60, '["想喝汤","清淡"]',              1),
-- 点心蒸笼 light-dimsum
('xiaolongbao',     '小笼包',       '面食', 0.76, '["想慢享","不吃辣"]',            1),
('xiajiao',         '水晶虾饺',     '粤式', 0.72, '["想慢享","清淡"]',              1),
('changfen',        '鲜虾肠粉',     '粤式', 0.72, '["要快","想吃冷的","清淡"]',      1);
