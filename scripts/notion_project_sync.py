#!/usr/bin/env python3
"""
Notion Project Sync - Bidirectional sync between Notion, local TODO.md, and GitHub

Syncs project tasks every 15 minutes to maintain a live roadmap in Notion.
Inspired by: /Users/devinmcgrath/Documents/GitHub/investment-analysis-platform/scripts/unified_sync.py
"""

import os
import asyncio
import json
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    from notion_client import AsyncClient
    NOTION_AVAILABLE = True
except ImportError:
    print("Warning: notion-client not installed. Run: pip install notion-client")
    NOTION_AVAILABLE = False


@dataclass
class Task:
    """Represents a project task"""
    title: str
    status: str = "Not Started"
    phase: str = ""
    priority: str = "Medium"
    category: str = ""
    progress: int = 0
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    notes: str = ""
    github_url: Optional[str] = None
    notion_page_id: Optional[str] = None
    local_id: Optional[str] = None


class ElectricityOptimizerNotionSync:
    """Manages bidirectional sync between Notion, local TODO.md, and GitHub"""

    def __init__(self, config_path: str = ".notion_sync_config.json"):
        self.config = self._load_config(config_path)
        self.notion = None
        self.database_id = None
        self.project_page_id = None

        if NOTION_AVAILABLE:
            self._initialize_notion_client()

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        full_path = Path(__file__).parent.parent / config_path

        if not full_path.exists():
            print(f"Config file not found: {full_path}")
            return {}

        with open(full_path, 'r') as f:
            return json.load(f)

    def _initialize_notion_client(self):
        """Initialize Notion API client"""
        api_key_env = self.config.get('notion', {}).get('api_key_env', 'NOTION_API_KEY')
        api_key = os.getenv(api_key_env)

        if not api_key:
            print(f"Warning: {api_key_env} not set. Notion sync disabled.")
            return

        self.notion = AsyncClient(auth=api_key)

        db_id_env = self.config.get('notion', {}).get('database_id_env', 'NOTION_DATABASE_ID')
        self.database_id = os.getenv(db_id_env)

        page_id_env = self.config.get('notion', {}).get('project_page_id_env', 'NOTION_PROJECT_PAGE_ID')
        self.project_page_id = os.getenv(page_id_env)

    def parse_todo_md(self, file_path: str = "TODO.md") -> List[Task]:
        """Parse local TODO.md file and extract tasks"""
        full_path = Path(__file__).parent.parent / file_path

        if not full_path.exists():
            print(f"TODO.md not found: {full_path}")
            return []

        with open(full_path, 'r') as f:
            content = f.read()

        tasks = []
        current_phase = ""
        current_section = ""

        lines = content.split('\n')
        for line in lines:
            # Detect phase headers
            if line.startswith('## Phase'):
                current_phase = line.replace('##', '').strip()
                continue

            # Detect section headers
            if line.startswith('###'):
                current_section = line.replace('###', '').strip()
                continue

            # Parse task lines
            if line.strip().startswith('- ['):
                # Extract checkbox status
                is_done = '[x]' in line or '[X]' in line
                status = "Done" if is_done else "Not Started"

                # Extract title
                title_match = re.search(r'\[.\] (.+)', line)
                if not title_match:
                    continue

                title = title_match.group(1).strip()

                # Determine category from section
                category = self._infer_category(current_section)

                # Determine priority (default to Medium)
                priority = "Medium"
                if "critical" in title.lower() or "security" in title.lower():
                    priority = "Critical"
                elif "testing" in title.lower() or "documentation" in title.lower():
                    priority = "Low"

                tasks.append(Task(
                    title=title,
                    status=status,
                    phase=current_phase,
                    category=category,
                    priority=priority,
                    progress=100 if is_done else 0
                ))

        return tasks

    def _infer_category(self, section_title: str) -> str:
        """Infer task category from section title"""
        section_lower = section_title.lower()

        if 'backend' in section_lower or 'api' in section_lower:
            return "Backend"
        elif 'frontend' in section_lower or 'ui' in section_lower:
            return "Frontend"
        elif 'ml' in section_lower or 'data' in section_lower or 'model' in section_lower:
            return "Data/ML"
        elif 'infrastructure' in section_lower or 'docker' in section_lower or 'devops' in section_lower:
            return "Infrastructure"
        elif 'security' in section_lower or 'compliance' in section_lower or 'gdpr' in section_lower:
            return "Security"
        elif 'testing' in section_lower or 'test' in section_lower:
            return "Testing"
        elif 'documentation' in section_lower or 'docs' in section_lower:
            return "Documentation"
        else:
            return "Backend"

    async def fetch_notion_tasks(self) -> List[Task]:
        """Fetch tasks from Notion database"""
        if not self.notion or not self.database_id:
            print("Notion client not initialized")
            return []

        try:
            response = await self.notion.databases.query(
                database_id=self.database_id,
                filter={
                    "property": "Status",
                    "select": {
                        "does_not_equal": "Archived"
                    }
                }
            )

            tasks = []
            for page in response.get('results', []):
                props = page.get('properties', {})

                # Extract properties
                title = self._extract_title(props.get('Title', {}))
                status = self._extract_select(props.get('Status', {}))
                phase = self._extract_select(props.get('Phase', {}))
                priority = self._extract_select(props.get('Priority', {}))
                category = self._extract_select(props.get('Category', {}))
                progress = self._extract_number(props.get('Progress', {}))
                start_date = self._extract_date(props.get('Start Date', {}))
                due_date = self._extract_date(props.get('Due Date', {}))
                github_url = self._extract_url(props.get('GitHub Issue', {}))

                tasks.append(Task(
                    title=title,
                    status=status or "Not Started",
                    phase=phase or "",
                    priority=priority or "Medium",
                    category=category or "",
                    progress=progress or 0,
                    start_date=start_date,
                    due_date=due_date,
                    github_url=github_url,
                    notion_page_id=page['id']
                ))

            return tasks

        except Exception as e:
            print(f"Error fetching Notion tasks: {e}")
            return []

    def _extract_title(self, prop: Dict) -> str:
        """Extract title from Notion property"""
        title_array = prop.get('title', [])
        if title_array:
            return title_array[0].get('text', {}).get('content', '')
        return ''

    def _extract_select(self, prop: Dict) -> Optional[str]:
        """Extract select value from Notion property"""
        select = prop.get('select')
        return select.get('name') if select else None

    def _extract_number(self, prop: Dict) -> Optional[int]:
        """Extract number from Notion property"""
        return prop.get('number')

    def _extract_date(self, prop: Dict) -> Optional[str]:
        """Extract date from Notion property"""
        date = prop.get('date')
        return date.get('start') if date else None

    def _extract_url(self, prop: Dict) -> Optional[str]:
        """Extract URL from Notion property"""
        return prop.get('url')

    def calculate_sync_updates(self, local_tasks: List[Task], notion_tasks: List[Task]) -> Dict[str, List[Dict]]:
        """Calculate what needs to be synced in each direction"""
        to_notion = []
        to_local = []

        # Create lookup dictionaries
        local_by_title = {task.title: task for task in local_tasks}
        notion_by_title = {task.title: task for task in notion_tasks}

        # Find tasks that exist locally but not in Notion (create in Notion)
        for title, local_task in local_by_title.items():
            if title not in notion_by_title:
                to_notion.append({
                    'action': 'create',
                    **asdict(local_task)
                })
            else:
                # Task exists in both - check if local is newer
                notion_task = notion_by_title[title]
                if local_task.status != notion_task.status or local_task.progress != notion_task.progress:
                    to_notion.append({
                        'action': 'update',
                        'page_id': notion_task.notion_page_id,
                        **asdict(local_task)
                    })

        # Find tasks that exist in Notion but not locally (create locally)
        for title, notion_task in notion_by_title.items():
            if title not in local_by_title:
                to_local.append({
                    'action': 'create',
                    **asdict(notion_task)
                })

        return {
            'to_notion': to_notion,
            'to_local': to_local
        }

    async def update_notion(self, updates: List[Dict]):
        """Push updates to Notion"""
        if not self.notion or not self.database_id:
            print("Notion client not initialized")
            return

        for task in updates:
            try:
                if task['action'] == 'create':
                    await self.notion.pages.create(
                        parent={'database_id': self.database_id},
                        properties=self._build_notion_properties(task)
                    )
                    print(f"✅ Created in Notion: {task['title']}")

                elif task['action'] == 'update':
                    await self.notion.pages.update(
                        page_id=task['page_id'],
                        properties=self._build_notion_properties(task)
                    )
                    print(f"🔄 Updated in Notion: {task['title']}")

            except Exception as e:
                print(f"❌ Error syncing to Notion: {task['title']} - {e}")

    def _build_notion_properties(self, task: Dict) -> Dict:
        """Build Notion properties dictionary"""
        properties = {
            'Title': {
                'title': [{'text': {'content': task['title']}}]
            },
            'Status': {
                'select': {'name': task['status']}
            },
            'Progress': {
                'number': task['progress']
            }
        }

        if task.get('phase'):
            properties['Phase'] = {'select': {'name': task['phase']}}

        if task.get('priority'):
            properties['Priority'] = {'select': {'name': task['priority']}}

        if task.get('category'):
            properties['Category'] = {'select': {'name': task['category']}}

        if task.get('start_date'):
            properties['Start Date'] = {'date': {'start': task['start_date']}}

        if task.get('due_date'):
            properties['Due Date'] = {'date': {'start': task['due_date']}}

        if task.get('github_url'):
            properties['GitHub Issue'] = {'url': task['github_url']}

        if task.get('notes'):
            properties['Notes'] = {
                'rich_text': [{'text': {'content': task['notes']}}]
            }

        return properties

    def update_local(self, updates: List[Dict]):
        """Update local TODO.md file"""
        # For now, we primarily sync from local -> Notion
        # Full bidirectional sync would require more complex TODO.md parsing
        print(f"ℹ️  {len(updates)} tasks would be synced to local (not implemented yet)")

    async def update_project_metrics(self):
        """Update high-level project metrics in Notion project page"""
        if not self.notion or not self.project_page_id:
            return

        try:
            # Fetch all tasks
            tasks = await self.fetch_notion_tasks()

            if not tasks:
                print("No tasks found for metrics calculation")
                return

            # Calculate metrics
            total_tasks = len(tasks)
            completed = len([t for t in tasks if t.status == 'Done'])
            in_progress = len([t for t in tasks if t.status == 'In Progress'])
            blocked = len([t for t in tasks if t.status == 'Blocked'])

            completion_percentage = (completed / total_tasks * 100) if total_tasks > 0 else 0

            # Update project page
            await self.notion.pages.update(
                page_id=self.project_page_id,
                properties={
                    'Total Tasks': {'number': total_tasks},
                    'Completed': {'number': completed},
                    'In Progress': {'number': in_progress},
                    'Blocked': {'number': blocked},
                    'Completion %': {'number': round(completion_percentage, 2)}
                }
            )

            print(f"📊 Metrics updated: {completed}/{total_tasks} tasks complete ({completion_percentage:.1f}%)")

        except Exception as e:
            print(f"❌ Error updating metrics: {e}")

    async def sync_project_status(self):
        """Main sync function - run every 15 minutes"""
        print(f"\n{'='*60}")
        print(f"🔄 Starting Notion sync at {datetime.now(timezone.utc).isoformat()}")
        print(f"{'='*60}\n")

        try:
            # Parse local tasks
            print("📖 Parsing local TODO.md...")
            local_tasks = self.parse_todo_md()
            print(f"   Found {len(local_tasks)} local tasks")

            # Fetch Notion tasks
            print("☁️  Fetching Notion tasks...")
            notion_tasks = await self.fetch_notion_tasks()
            print(f"   Found {len(notion_tasks)} Notion tasks")

            # Calculate sync updates
            print("🔍 Calculating sync updates...")
            updates = self.calculate_sync_updates(local_tasks, notion_tasks)
            print(f"   To Notion: {len(updates['to_notion'])} tasks")
            print(f"   To Local: {len(updates['to_local'])} tasks")

            # Apply updates
            if updates['to_notion']:
                print("\n📤 Syncing to Notion...")
                await self.update_notion(updates['to_notion'])

            if updates['to_local']:
                print("\n📥 Syncing to Local...")
                self.update_local(updates['to_local'])

            # Update project metrics
            print("\n📊 Updating project metrics...")
            await self.update_project_metrics()

            print(f"\n✅ Sync completed successfully\n")

        except Exception as e:
            print(f"\n❌ Sync error: {e}\n")


async def main():
    """Main entry point - runs continuous sync"""
    sync = ElectricityOptimizerNotionSync()

    if not NOTION_AVAILABLE:
        print("Notion client not available. Install with: pip install notion-client")
        return

    # Get sync interval from config (default 15 minutes)
    sync_interval = sync.config.get('notion', {}).get('sync_interval_seconds', 900)

    print(f"🚀 Starting Notion sync daemon (interval: {sync_interval}s)")

    while True:
        try:
            await sync.sync_project_status()
        except KeyboardInterrupt:
            print("\n⏹️  Sync daemon stopped by user")
            break
        except Exception as e:
            print(f"❌ Unexpected error: {e}")

        # Wait for next sync
        print(f"⏱️  Next sync in {sync_interval // 60} minutes...")
        await asyncio.sleep(sync_interval)


if __name__ == '__main__':
    asyncio.run(main())
