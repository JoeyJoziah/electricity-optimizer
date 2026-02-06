#!/usr/bin/env python3
"""
Notion Sync Script for Electricity Optimizer
Provides bidirectional sync between Notion, TODO.md, and GitHub Issues
Based on patterns from investment-analysis-platform
"""

import json
import os
import re
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import requests

class NotionSync:
    def __init__(self, config_path: str = ".notion_sync_config.json"):
        self.project_root = Path(__file__).parent.parent
        self.config_path = self.project_root / config_path
        self.config = self._load_config()
        self.api_key = self._load_api_key()
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": "2025-09-03",
            "Content-Type": "application/json"
        }
        
    def _load_config(self) -> Dict:
        with open(self.config_path) as f:
            return json.load(f)
            
    def _load_api_key(self) -> str:
        key_path = Path(self.config['notion']['api_key_path']).expanduser()
        return key_path.read_text().strip()
        
    def parse_todo_md(self) -> List[Dict]:
        """Parse TODO.md into structured tasks"""
        todo_path = self.project_root / self.config['local']['todo_file']
        content = todo_path.read_text()
        
        tasks = []
        current_phase = None
        current_section = None
        
        lines = content.split('\n')
        for line in lines:
            # Detect phase
            if line.startswith('## Phase'):
                phase_match = re.search(r'Phase \d+: (.+)', line)
                if phase_match:
                    current_phase = line.strip('# ').split(' (')[0]
                    
            # Detect section
            elif line.startswith('###'):
                current_section = line.strip('# ').strip()
                
            # Parse task
            elif line.strip().startswith('- [ ]') or line.strip().startswith('- [x]'):
                is_done = '[x]' in line
                task_text = line.split(']', 1)[1].strip()
                
                task = {
                    'title': task_text,
                    'status': 'Done' if is_done else self._infer_status(current_section),
                    'phase': current_phase,
                    'priority': self._infer_priority(task_text),
                    'category': self._infer_category(task_text, current_phase),
                    'progress': 100 if is_done else 0,
                    'milestone': 'MVP'
                }
                tasks.append(task)
                
        return tasks
        
    def _infer_status(self, section: str) -> str:
        """Infer status from section header"""
        if not section:
            return 'Not Started'
        section_lower = section.lower()
        if 'completed' in section_lower or '✅' in section:
            return 'Done'
        elif 'in progress' in section_lower or '🟡' in section:
            return 'In Progress'
        elif 'not started' in section_lower or '🔴' in section:
            return 'Not Started'
        return 'Not Started'
        
    def _infer_priority(self, task_text: str) -> str:
        """Infer priority from task text"""
        task_lower = task_text.lower()
        if any(word in task_lower for word in ['critical', 'urgent', 'security', 'gdpr', 'auth']):
            return 'Critical'
        elif any(word in task_lower for word in ['api', 'database', 'model', 'frontend']):
            return 'High'
        elif any(word in task_lower for word in ['test', 'monitoring', 'documentation']):
            return 'Medium'
        return 'Low'
        
    def _infer_category(self, task_text: str, phase: str) -> str:
        """Infer category from task text and phase"""
        task_lower = task_text.lower()
        
        if any(word in task_lower for word in ['fastapi', 'api', 'backend', 'supabase', 'redis']):
            return 'Backend'
        elif any(word in task_lower for word in ['next.js', 'react', 'frontend', 'dashboard', 'ui']):
            return 'Frontend'
        elif any(word in task_lower for word in ['ml', 'model', 'cnn', 'lstm', 'forecast', 'airflow', 'data']):
            return 'Data/ML'
        elif any(word in task_lower for word in ['docker', 'ci/cd', 'prometheus', 'infrastructure']):
            return 'Infrastructure'
        elif any(word in task_lower for word in ['security', 'auth', 'gdpr', 'compliance']):
            return 'Security'
        elif any(word in task_lower for word in ['test', 'testing', 'qa']):
            return 'Testing'
        elif any(word in task_lower for word in ['documentation', 'docs']):
            return 'Documentation'
            
        # Fallback to phase-based inference
        if phase and 'Backend' in phase:
            return 'Backend'
        elif phase and 'Frontend' in phase:
            return 'Frontend'
        elif phase and 'ML' in phase or 'Data' in phase:
            return 'Data/ML'
            
        return 'Backend'
        
    def fetch_notion_tasks(self) -> List[Dict]:
        """Fetch all tasks from Notion database"""
        data_source_id = self.config['notion']['data_source_id']
        url = f"https://api.notion.com/v1/data_sources/{data_source_id}/query"
        
        response = requests.post(url, headers=self.headers, json={})
        response.raise_for_status()
        
        results = response.json().get('results', [])
        
        tasks = []
        for page in results:
            props = page['properties']
            task = {
                'page_id': page['id'],
                'title': self._extract_title(props.get('Title', {})),
                'status': self._extract_select(props.get('Status', {})),
                'phase': self._extract_select(props.get('Phase', {})),
                'priority': self._extract_select(props.get('Priority', {})),
                'category': self._extract_select(props.get('Category', {})),
                'milestone': self._extract_select(props.get('Milestone', {})),
                'assignee': self._extract_select(props.get('Assignee', {})),
                'progress': props.get('Progress', {}).get('number', 0),
                'start_date': self._extract_date(props.get('Start Date', {})),
                'due_date': self._extract_date(props.get('Due Date', {})),
                'notes': self._extract_rich_text(props.get('Notes', {})),
                'github_issue': props.get('GitHub Issue', {}).get('url'),
                'related_prs': props.get('Related PRs', {}).get('url')
            }
            tasks.append(task)
            
        return tasks
        
    def _extract_title(self, prop: Dict) -> str:
        title_list = prop.get('title', [])
        if title_list:
            return title_list[0].get('plain_text', '')
        return ''
        
    def _extract_select(self, prop: Dict) -> Optional[str]:
        select = prop.get('select')
        if select:
            return select.get('name')
        return None
        
    def _extract_date(self, prop: Dict) -> Optional[str]:
        date = prop.get('date')
        if date:
            return date.get('start')
        return None
        
    def _extract_rich_text(self, prop: Dict) -> str:
        rich_text_list = prop.get('rich_text', [])
        if rich_text_list:
            return rich_text_list[0].get('plain_text', '')
        return ''
        
    def create_notion_task(self, task: Dict) -> Dict:
        """Create a new task in Notion"""
        database_id = self.config['notion']['database_id']
        url = "https://api.notion.com/v1/pages"
        
        properties = {
            "Title": {"title": [{"text": {"content": task['title']}}]},
            "Status": {"select": {"name": task.get('status', 'Not Started')}},
            "Priority": {"select": {"name": task.get('priority', 'Medium')}},
            "Category": {"select": {"name": task.get('category', 'Backend')}},
            "Progress": {"number": task.get('progress', 0)},
            "Milestone": {"select": {"name": task.get('milestone', 'MVP')}}
        }
        
        if task.get('phase'):
            properties["Phase"] = {"select": {"name": task['phase']}}
        if task.get('assignee'):
            properties["Assignee"] = {"select": {"name": task['assignee']}}
        if task.get('notes'):
            properties["Notes"] = {"rich_text": [{"text": {"content": task['notes']}}]}
            
        payload = {
            "parent": {"database_id": database_id},
            "properties": properties
        }
        
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()
        
    def update_notion_task(self, page_id: str, updates: Dict) -> Dict:
        """Update an existing Notion task"""
        url = f"https://api.notion.com/v1/pages/{page_id}"
        
        properties = {}
        if 'status' in updates:
            properties["Status"] = {"select": {"name": updates['status']}}
        if 'progress' in updates:
            properties["Progress"] = {"number": updates['progress']}
        if 'notes' in updates:
            properties["Notes"] = {"rich_text": [{"text": {"content": updates['notes']}}]}
            
        payload = {"properties": properties}
        
        response = requests.patch(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()
        
    def sync_to_notion(self):
        """Sync TODO.md tasks to Notion"""
        print(f"[{datetime.now()}] Starting sync to Notion...")
        
        local_tasks = self.parse_todo_md()
        notion_tasks = self.fetch_notion_tasks()
        
        # Build mapping of existing tasks by title
        notion_task_map = {task['title']: task for task in notion_tasks}
        
        created = 0
        updated = 0
        
        for local_task in local_tasks:
            title = local_task['title']
            
            if title in notion_task_map:
                # Update existing task
                notion_task = notion_task_map[title]
                if notion_task['status'] != local_task['status'] or \
                   notion_task['progress'] != local_task['progress']:
                    self.update_notion_task(notion_task['page_id'], {
                        'status': local_task['status'],
                        'progress': local_task['progress']
                    })
                    updated += 1
            else:
                # Create new task
                self.create_notion_task(local_task)
                created += 1
                
        print(f"[{datetime.now()}] Sync complete: {created} created, {updated} updated")
        
    def run_continuous(self):
        """Run continuous sync every N minutes"""
        interval = self.config['notion']['sync_interval_minutes']
        print(f"Starting continuous sync (every {interval} minutes)...")
        print(f"Database URL: {self.config['notion']['database_url']}")
        print("Press Ctrl+C to stop\n")
        
        while True:
            try:
                self.sync_to_notion()
            except Exception as e:
                print(f"[{datetime.now()}] Sync error: {e}")
                
            import time
            time.sleep(interval * 60)

def main():
    import sys
    
    sync = NotionSync()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        sync.sync_to_notion()
    else:
        sync.run_continuous()

if __name__ == '__main__':
    main()
