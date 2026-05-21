"""Unit tests for context manager."""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from src.dagdi.context import manager, storage


class TestSetContext:
    """Tests for setting context."""
    
    def test_set_context_success(self):
        """Should set context successfully."""
        with TemporaryDirectory() as tmpdir:
            storage_file = Path(tmpdir) / "context.json"
            
            with patch('src.dagdi.context.storage.get_storage_path') as mock_path:
                mock_path.return_value = storage_file
                
                name = manager.set_context("myapp", "production")
                
                assert name == "myapp-production"
    
    def test_set_context_with_name(self):
        """Should set context with custom name."""
        with TemporaryDirectory() as tmpdir:
            storage_file = Path(tmpdir) / "context.json"
            
            with patch('src.dagdi.context.storage.get_storage_path') as mock_path:
                mock_path.return_value = storage_file
                
                name = manager.set_context("myapp", "production", "prod")
                
                assert name == "prod"
    
    def test_set_context_storage_error(self):
        """Should raise ContextError on storage error."""
        with patch('src.dagdi.context.storage.set_context') as mock_set:
            mock_set.side_effect = storage.StorageError("Storage failed")
            
            with pytest.raises(manager.ContextError) as exc_info:
                manager.set_context("myapp", "production")
            
            assert "Failed to set context" in str(exc_info.value)


class TestGetContext:
    """Tests for getting context."""
    
    def test_get_context_when_set(self):
        """Should return context when set."""
        with TemporaryDirectory() as tmpdir:
            storage_file = Path(tmpdir) / "context.json"
            
            with patch('src.dagdi.context.storage.get_storage_path') as mock_path:
                mock_path.return_value = storage_file
                
                manager.set_context("myapp", "production")
                context = manager.get_context()
                
                assert context is not None
                assert context["product"] == "myapp"
                assert context["environment"] == "production"
    
    def test_get_context_when_not_set(self):
        """Should return None when no context."""
        with TemporaryDirectory() as tmpdir:
            storage_file = Path(tmpdir) / "context.json"
            
            with patch('src.dagdi.context.storage.get_storage_path') as mock_path:
                mock_path.return_value = storage_file
                
                context = manager.get_context()
                
                assert context is None
    
    def test_get_context_storage_error(self):
        """Should raise ContextError on storage error."""
        with patch('src.dagdi.context.storage.get_current_context') as mock_get:
            mock_get.side_effect = storage.StorageError("Storage failed")
            
            with pytest.raises(manager.ContextError) as exc_info:
                manager.get_context()
            
            assert "Failed to get context" in str(exc_info.value)


class TestResetContext:
    """Tests for resetting context."""
    
    def test_reset_context_success(self):
        """Should reset context successfully."""
        with TemporaryDirectory() as tmpdir:
            storage_file = Path(tmpdir) / "context.json"
            
            with patch('src.dagdi.context.storage.get_storage_path') as mock_path:
                mock_path.return_value = storage_file
                
                manager.set_context("myapp", "production")
                manager.reset_context()
                
                context = manager.get_context()
                assert context is None
    
    def test_reset_context_storage_error(self):
        """Should raise ContextError on storage error."""
        with patch('src.dagdi.context.storage.reset_context') as mock_reset:
            mock_reset.side_effect = storage.StorageError("Storage failed")
            
            with pytest.raises(manager.ContextError) as exc_info:
                manager.reset_context()
            
            assert "Failed to reset context" in str(exc_info.value)


class TestListContexts:
    """Tests for listing contexts."""
    
    def test_list_contexts_empty(self):
        """Should return empty dict when no contexts."""
        with TemporaryDirectory() as tmpdir:
            storage_file = Path(tmpdir) / "context.json"
            
            with patch('src.dagdi.context.storage.get_storage_path') as mock_path:
                mock_path.return_value = storage_file
                
                contexts = manager.list_contexts()
                
                assert contexts == {}
    
    def test_list_contexts_multiple(self):
        """Should return all contexts."""
        with TemporaryDirectory() as tmpdir:
            storage_file = Path(tmpdir) / "context.json"
            
            with patch('src.dagdi.context.storage.get_storage_path') as mock_path:
                mock_path.return_value = storage_file
                
                manager.set_context("app1", "dev", "dev")
                manager.set_context("app1", "prod", "prod")
                
                contexts = manager.list_contexts()
                
                assert len(contexts) == 2
                assert "dev" in contexts
                assert "prod" in contexts
    
    def test_list_contexts_storage_error(self):
        """Should raise ContextError on storage error."""
        with patch('src.dagdi.context.storage.list_all_contexts') as mock_list:
            mock_list.side_effect = storage.StorageError("Storage failed")
            
            with pytest.raises(manager.ContextError) as exc_info:
                manager.list_contexts()
            
            assert "Failed to list contexts" in str(exc_info.value)


class TestSwitchContext:
    """Tests for switching context."""
    
    def test_switch_context_valid(self):
        """Should switch to valid context."""
        with TemporaryDirectory() as tmpdir:
            storage_file = Path(tmpdir) / "context.json"
            
            with patch('src.dagdi.context.storage.get_storage_path') as mock_path:
                mock_path.return_value = storage_file
                
                manager.set_context("app1", "dev", "dev")
                manager.set_context("app1", "prod", "prod")
                
                manager.switch_context("dev")
                
                context = manager.get_context()
                assert context["product"] == "app1"
                assert context["environment"] == "dev"
    
    def test_switch_context_invalid(self):
        """Should raise ContextError for invalid context."""
        with TemporaryDirectory() as tmpdir:
            storage_file = Path(tmpdir) / "context.json"
            
            with patch('src.dagdi.context.storage.get_storage_path') as mock_path:
                mock_path.return_value = storage_file
                
                with pytest.raises(manager.ContextError) as exc_info:
                    manager.switch_context("nonexistent")
                
                assert "Failed to switch context" in str(exc_info.value)
    
    def test_switch_context_storage_error(self):
        """Should raise ContextError on storage error."""
        with patch('src.dagdi.context.storage.switch_context') as mock_switch:
            mock_switch.side_effect = storage.StorageError("Storage failed")
            
            with pytest.raises(manager.ContextError) as exc_info:
                manager.switch_context("dev")
            
            assert "Failed to switch context" in str(exc_info.value)


class TestGetCurrentContextName:
    """Tests for getting current context name."""
    
    def test_get_current_context_name_when_set(self):
        """Should return context name when set."""
        with TemporaryDirectory() as tmpdir:
            storage_file = Path(tmpdir) / "context.json"
            
            with patch('src.dagdi.context.storage.get_storage_path') as mock_path:
                mock_path.return_value = storage_file
                
                manager.set_context("myapp", "production", "prod")
                name = manager.get_current_context_name()
                
                assert name == "prod"
    
    def test_get_current_context_name_when_not_set(self):
        """Should return None when no context."""
        with TemporaryDirectory() as tmpdir:
            storage_file = Path(tmpdir) / "context.json"
            
            with patch('src.dagdi.context.storage.get_storage_path') as mock_path:
                mock_path.return_value = storage_file
                
                name = manager.get_current_context_name()
                
                assert name is None
    
    def test_get_current_context_name_storage_error(self):
        """Should raise ContextError on storage error."""
        with patch('src.dagdi.context.storage.get_current_context_name') as mock_get:
            mock_get.side_effect = storage.StorageError("Storage failed")
            
            with pytest.raises(manager.ContextError) as exc_info:
                manager.get_current_context_name()
            
            assert "Failed to get context name" in str(exc_info.value)
