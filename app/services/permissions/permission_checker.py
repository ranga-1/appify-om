"""Permission checker for IAM-style permission validation."""

import re
from typing import List, Dict, Optional, Set
from enum import Enum


class FieldAccess(str, Enum):
    """Field access levels."""
    READ = "read"
    WRITE = "write"
    MASK = "mask"
    HIDE = "hide"


class Scope(str, Enum):
    """Data access scopes."""
    SELF = "self"
    TEAM = "team"
    DEPARTMENT = "department"
    ALL = "all"
    NONE = "none"


class PermissionChecker:
    """
    Validates IAM-style permissions with wildcard support.
    
    Permission Format: "resource:action:modifier:value"
    Examples:
        - data:read:scope:all
        - data:*
        - bulk:export:format:csv
        - field:read:abc12_salary
        - admin:*
        
    Wildcard Rules:
        - "*" matches any segment
        - More specific permissions take precedence
        - "data:*" matches "data:read", "data:create", etc.
    """
    
    @staticmethod
    def has_permission(user_permissions: List[str], required: str) -> bool:
        """
        Check if user has the required permission.
        
        Args:
            user_permissions: List of permission strings user has
            required: Required permission string
            
        Returns:
            True if user has permission (direct match or wildcard)
            
        Examples:
            >>> has_permission(["data:*"], "data:read")
            True
            >>> has_permission(["data:read:scope:team"], "data:read:scope:all")
            False
            >>> has_permission(["admin:*"], "admin:delete:users")
            True
        """
        if not user_permissions:
            return False
            
        # Direct match
        if required in user_permissions:
            return True
        
        # Check wildcard matches
        required_parts = required.split(":")
        
        for permission in user_permissions:
            if PermissionChecker._matches_pattern(permission, required_parts):
                return True
        
        return False
    
    @staticmethod
    def _matches_pattern(pattern: str, required_parts: List[str]) -> bool:
        """
        Check if a permission pattern matches the required permission.
        
        Args:
            pattern: Permission pattern (may contain wildcards)
            required_parts: Required permission split by ":"
            
        Returns:
            True if pattern matches
        """
        pattern_parts = pattern.split(":")
        
        # If pattern is shorter, it can only match if it ends with *
        if len(pattern_parts) > len(required_parts):
            return False
        
        for i, pattern_part in enumerate(pattern_parts):
            if pattern_part == "*":
                # Wildcard matches rest of the string
                return True
            
            if i >= len(required_parts):
                return False
            
            if pattern_part != required_parts[i]:
                return False
        
        # All parts matched and lengths equal
        return len(pattern_parts) == len(required_parts)
    
    @staticmethod
    def get_data_scope(permissions: List[str], action: str = "read") -> Scope:
        """
        Extract the most permissive data scope for an action.
        
        Args:
            permissions: List of permission strings
            action: Action to check (read, create, update, delete)
            
        Returns:
            Highest scope level (all > department > team > self > none)
            
        Examples:
            >>> get_data_scope(["data:read:scope:team"], "read")
            Scope.TEAM
            >>> get_data_scope(["data:*"], "update")
            Scope.ALL  # Wildcard grants all scope
        """
        scope_hierarchy = {
            Scope.NONE: 0,
            Scope.SELF: 1,
            Scope.TEAM: 2,
            Scope.DEPARTMENT: 3,
            Scope.ALL: 4,
        }
        
        max_scope = Scope.NONE
        max_scope_level = 0
        
        for permission in permissions:
            # Check for wildcard grants
            if permission == "data:*" or permission == "admin:*":
                return Scope.ALL
            
            # Check specific action scope
            parts = permission.split(":")
            if len(parts) >= 4 and parts[0] == "data" and parts[1] == action and parts[2] == "scope":
                scope_value = parts[3]
                try:
                    scope = Scope(scope_value)
                    scope_level = scope_hierarchy.get(scope, 0)
                    if scope_level > max_scope_level:
                        max_scope_level = scope_level
                        max_scope = scope
                except ValueError:
                    # Invalid scope value, skip
                    continue
            
            # Check wildcard action grants
            if len(parts) >= 4 and parts[0] == "data" and parts[1] == "*" and parts[2] == "scope":
                scope_value = parts[3]
                try:
                    scope = Scope(scope_value)
                    scope_level = scope_hierarchy.get(scope, 0)
                    if scope_level > max_scope_level:
                        max_scope_level = scope_level
                        max_scope = scope
                except ValueError:
                    continue
        
        return max_scope
    
    @staticmethod
    def filter_fields(
        permissions: List[str], 
        all_fields: List[str],
        object_prefix: Optional[str] = None
    ) -> Dict[str, FieldAccess]:
        """
        Determine access level for each field based on permissions.
        
        Args:
            permissions: List of permission strings
            all_fields: List of all available field names
            object_prefix: Object prefix (e.g., "abc12") for field permissions
            
        Returns:
            Dictionary mapping field name to access level
            
        Examples:
            >>> filter_fields(["field:read:*"], ["name", "salary"])
            {"name": "read", "salary": "read"}
            >>> filter_fields(["field:read:*", "field:mask:salary"], ["name", "salary"])
            {"name": "read", "salary": "mask"}
        """
        field_access: Dict[str, FieldAccess] = {}
        
        # Initialize all fields as hidden by default (fail-closed)
        for field in all_fields:
            field_access[field] = FieldAccess.HIDE
        
        # Check for admin wildcard (grants full access)
        if "admin:*" in permissions or "field:*" in permissions:
            for field in all_fields:
                field_access[field] = FieldAccess.WRITE
            return field_access
        
        # Process field permissions (more specific beats less specific)
        for permission in permissions:
            parts = permission.split(":")
            
            if len(parts) < 2 or parts[0] != "field":
                continue
            
            access_type = parts[1]  # read, write, mask, hide
            
            if len(parts) >= 3:
                field_pattern = parts[2]
                
                # Handle wildcards
                if field_pattern == "*":
                    # Apply to all fields
                    try:
                        access = FieldAccess(access_type)
                        for field in all_fields:
                            # Only upgrade access level, don't downgrade
                            current = field_access[field]
                            if PermissionChecker._is_higher_access(access, current):
                                field_access[field] = access
                    except ValueError:
                        # Invalid access type, skip
                        continue
                else:
                    # Specific field
                    # Remove object prefix if present in permission
                    if object_prefix and field_pattern.startswith(f"{object_prefix}_"):
                        field_name = field_pattern
                    else:
                        # Permission might be without prefix
                        field_name = field_pattern
                        # Also try with prefix
                        if object_prefix:
                            prefixed_name = f"{object_prefix}_{field_pattern}"
                            if prefixed_name in all_fields:
                                field_name = prefixed_name
                    
                    if field_name in all_fields:
                        try:
                            access = FieldAccess(access_type)
                            # Specific permissions override wildcards
                            field_access[field_name] = access
                        except ValueError:
                            continue
        
        return field_access
    
    @staticmethod
    def _is_higher_access(new_access: FieldAccess, current_access: FieldAccess) -> bool:
        """
        Check if new access level is higher than current.
        
        Hierarchy: WRITE > READ > MASK > HIDE
        """
        hierarchy = {
            FieldAccess.HIDE: 0,
            FieldAccess.MASK: 1,
            FieldAccess.READ: 2,
            FieldAccess.WRITE: 3,
        }
        return hierarchy.get(new_access, 0) > hierarchy.get(current_access, 0)
    
    @staticmethod
    def can_bulk_operation(permissions: List[str], operation: str) -> bool:
        """
        Check if user can perform bulk operation.
        
        Args:
            permissions: List of permission strings
            operation: Bulk operation (import, export, delete, update)
            
        Returns:
            True if user has bulk permission
            
        Examples:
            >>> can_bulk_operation(["bulk:export:format:csv"], "export")
            True
            >>> can_bulk_operation(["bulk:*"], "import")
            True
        """
        # Check admin wildcard
        if "admin:*" in permissions:
            return True
        
        # Check bulk wildcard
        if "bulk:*" in permissions:
            return True
        
        # Check specific bulk operation
        required = f"bulk:{operation}"
        return PermissionChecker.has_permission(permissions, required)
    
    @staticmethod
    def can_use_query_type(permissions: List[str], query_type: str) -> bool:
        """
        Check if user can use specific query type.
        
        Args:
            permissions: List of permission strings
            query_type: Query type (basic, advanced, aggregation)
            
        Returns:
            True if user has query permission
            
        Examples:
            >>> can_use_query_type(["query:basic"], "basic")
            True
            >>> can_use_query_type(["query:advanced"], "aggregation")
            False
        """
        # Check admin wildcard
        if "admin:*" in permissions:
            return True
        
        # Check query wildcard
        if "query:*" in permissions:
            return True
        
        # Check specific query type
        required = f"query:{query_type}"
        return PermissionChecker.has_permission(permissions, required)
    
    @staticmethod
    def get_export_formats(permissions: List[str]) -> Set[str]:
        """
        Get allowed export formats for user.
        
        Args:
            permissions: List of permission strings
            
        Returns:
            Set of allowed format codes (csv, json, excel, parquet)
            
        Examples:
            >>> get_export_formats(["bulk:export:format:csv"])
            {"csv"}
            >>> get_export_formats(["bulk:export:format:*"])
            {"csv", "json", "excel", "parquet"}
        """
        formats = set()
        
        # Check admin wildcard
        if "admin:*" in permissions:
            return {"csv", "json", "excel", "parquet"}
        
        # Check bulk export wildcard
        if "bulk:export:format:*" in permissions:
            return {"csv", "json", "excel", "parquet"}
        
        # Check specific formats
        for permission in permissions:
            parts = permission.split(":")
            if len(parts) == 4 and parts[0] == "bulk" and parts[1] == "export" and parts[2] == "format":
                format_code = parts[3]
                if format_code in {"csv", "json", "excel", "parquet"}:
                    formats.add(format_code)
        
        return formats
