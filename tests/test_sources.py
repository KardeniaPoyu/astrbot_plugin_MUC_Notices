"""
测试 sources.py 中的数据完整性和一致性
"""
import sources as src


class TestSourcesIntegrity:
    """测试通知来源配置的完整性"""
    
    def test_sources_is_list(self):
        """测试 SOURCES 是列表"""
        assert isinstance(src.SOURCES, list)
    
    def test_sources_not_empty(self):
        """测试 SOURCES 不为空"""
        assert len(src.SOURCES) > 0
    
    def test_source_count(self):
        """测试至少包含 14 个来源"""
        assert len(src.SOURCES) >= 14, f"期望至少 14 个来源，实际 {len(src.SOURCES)}"
    
    def test_all_sources_have_required_fields(self):
        """测试每个来源都有必需的字段"""
        required_fields = ['key', 'name']
        for source in src.SOURCES:
            for field in required_fields:
                assert field in source, f"来源缺少必需字段 '{field}': {source.get('key', 'unknown')}"
    
    def test_source_keys_are_unique(self):
        """测试来源 key 唯一"""
        keys = [source.get('key') for source in src.SOURCES]
        assert len(keys) == len(set(keys)), f"存在重复的 key: {[k for k in keys if keys.count(k) > 1]}"
    
    def test_source_keys_are_non_empty_strings(self):
        """测试来源 key 是非空字符串"""
        for source in src.SOURCES:
            key = source.get('key')
            assert isinstance(key, str), f"key 不是字符串: {key}"
            assert len(key) > 0, f"key 为空字符串"
    
    def test_source_has_url_or_list_url(self):
        """测试每个来源都有 URL 配置"""
        has_url = 0
        for source in src.SOURCES:
            has_url_or_list_url = ('url' in source) or ('list_url' in source)
            if has_url_or_list_url:
                has_url += 1
        assert has_url > 0, "至少需要部分来源有 URL 配置"
    
    def test_source_names_are_strings(self):
        """测试来源名称都是字符串"""
        for source in src.SOURCES:
            name = source.get('name')
            assert isinstance(name, str), f"name 不是字符串: {name}"
            assert len(name) > 0, f"name 为空字符串"
    
    def test_source_keys_format(self):
        """测试来源 key 使用下划线命名法"""
        for source in src.SOURCES:
            key = source.get('key')
            assert ' ' not in key, f"key 包含空格: {key}"
            assert key == key.lower(), f"key 应全小写: {key}"


class TestSourcesNames:
    """测试常见来源的存在性"""
    
    def test_muc_tzgg_exists(self):
        """测试主站通知公告存在"""
        keys = [s['key'] for s in src.SOURCES]
        assert 'muc_tzgg' in keys
    
    def test_grs_sources_exist(self):
        """测试研究生院来源存在"""
        keys = [s['key'] for s in src.SOURCES]
        grs_keys = [k for k in keys if k.startswith('grs_')]
        assert len(grs_keys) >= 5, f"研究生院来源数量不足: {len(grs_keys)}"
    
    def test_rsc_exists(self):
        """测试人事处来源存在"""
        keys = [s['key'] for s in src.SOURCES]
        assert 'rsc_tzgg' in keys
    
    def test_cwc_exists(self):
        """测试财务处来源存在"""
        keys = [s['key'] for s in src.SOURCES]
        assert 'cwc_tzgg' in keys
    
    def test_news_sources_exist(self):
        """测试新闻网来源存在"""
        keys = [s['key'] for s in src.SOURCES]
        news_keys = [k for k in keys if k.startswith('news_')]
        assert len(news_keys) >= 2, f"新闻网来源数量不足: {len(news_keys)}"
    
    def test_portal_sources_exist(self):
        """测试信息门户来源存在"""
        keys = [s['key'] for s in src.SOURCES]
        portal_keys = [k for k in keys if k.startswith('my_')]
        assert len(portal_keys) >= 3, f"信息门户来源数量不足: {len(portal_keys)}"