# utils/config_generator.py

import json
import base64
import logging
import uuid
import datetime
from urllib.parse import quote

from utils.helpers import generate_random_string

logger = logging.getLogger(__name__)

class ConfigGenerator:
    def __init__(self, xui_api_client, db_manager):
        self.xui_api = xui_api_client
        self.db_manager = db_manager
        logger.info("ConfigGenerator initialized.")

    def create_client_and_configs(self, user_telegram_id: int, server_id: int, total_gb: float, duration_days: int or None):
        """
        کلاینت را در پنل X-UI ایجاد می‌کند و لینک سابسکریپشن و کانفیگ‌های تکی را برمی‌گرداند.
        """
        logger.info(f"Starting config generation for user:{user_telegram_id} on server:{server_id}")

        server_data = self.db_manager.get_server_by_id(server_id)
        if not server_data:
            logger.error(f"Server {server_id} not found.")
            return None, None, None

        # --- بخش اصلاح شده ---
        # فراخوانی مستقیم کلاس برای ساخت نمونه جدید، بدون استفاده از type()
        temp_xui_client = self.xui_api(
            panel_url=server_data['panel_url'],
            username=server_data['username'],
            password=server_data['password']
        )
        # --- پایان بخش اصلاح شده ---

        if not temp_xui_client.login():
            logger.error(f"Failed to login to X-UI panel for server {server_data['name']}.")
            return None, None, None

        # --- ۱. آماده‌سازی اطلاعات کلاینت ---
        master_sub_id = generate_random_string(12)
        expiry_time_ms = 0
        if duration_days is not None and duration_days > 0:
            expire_date = datetime.datetime.now() + datetime.timedelta(days=duration_days)
            expiry_time_ms = int(expire_date.timestamp() * 1000)
        
        total_traffic_bytes = int(total_gb * (1024**3)) if total_gb is not None else 0

        # --- ۲. دریافت اینباندهای فعال از دیتابیس ربات ---
        active_inbounds_from_db = self.db_manager.get_server_inbounds(server_id, only_active=True)
        if not active_inbounds_from_db:
            logger.error(f"No active inbounds configured for server {server_id} in bot's DB.")
            return None, None, None

        all_generated_configs = []
        representative_client_uuid = ""
        representative_client_email = ""

        # --- ۳. حلقه روی اینباندها و ساخت کلاینت در پنل ---
        for db_inbound in active_inbounds_from_db:
            inbound_id_on_panel = db_inbound['inbound_id']
            client_uuid = str(uuid.uuid4())
            client_email = f"u{user_telegram_id}.s{server_id}.{generate_random_string(4)}"

            if not representative_client_uuid:
                representative_client_uuid = client_uuid
                representative_client_email = client_email

            client_settings = {
                "id": client_uuid,
                "email": client_email,
                "flow": "",
                "totalGB": total_traffic_bytes,
                "expiryTime": expiry_time_ms,
                "enable": True,
                "tgId": str(user_telegram_id),
                "subId": master_sub_id,
            }

            add_client_payload = {
                "id": inbound_id_on_panel,
                "settings": json.dumps({"clients": [client_settings]})
            }
            
            logger.info(f"Adding client {client_email} to inbound {inbound_id_on_panel}...")
            if not temp_xui_client.add_client(add_client_payload):
                logger.error(f"Failed to add client to inbound {inbound_id_on_panel}. Aborting.")
                return None, None, None

            # --- ۴. ساخت کانفیگ تکی برای کلاینت ایجاد شده ---
            inbound_details = temp_xui_client.get_inbound(inbound_id_on_panel)
            if not inbound_details:
                logger.warning(f"Could not get details for inbound {inbound_id_on_panel}. Skipping single config.")
                continue

            single_config_url = self._generate_single_config_url(
                client_uuid=client_uuid,
                server_data=server_data,
                inbound_panel_details=inbound_details
            )
            if single_config_url:
                all_generated_configs.append(single_config_url)
        
        # --- ۵. ساخت لینک نهایی سابسکریپشن ---
        sub_base_url = server_data['subscription_base_url'].rstrip('/')
        sub_path = server_data['subscription_path_prefix'].strip('/')
        subscription_link = f"{sub_base_url}/{sub_path}/{master_sub_id}"
        print(f"--- DEBUG LINK GENERATION ---\nBase URL: {sub_base_url}\nPath: {sub_path}\nSub ID: {master_sub_id}\nFinal Link: {subscription_link}\n-----------------------------")

        client_details_for_db = {
            "uuid": representative_client_uuid,
            "email": representative_client_email,
            "subscription_id": master_sub_id
        }

        logger.info(f"Config generation successful. Sub link: {subscription_link}")
        return client_details_for_db, subscription_link, all_generated_configs

    def _generate_single_config_url(self, client_uuid: str, server_data: dict, inbound_panel_details: dict) -> dict or None:
        """
        بر اساس جزئیات اینباند و کلاینت، یک کانفیگ تکی تولید می‌کند.
        """
        try:
            protocol = inbound_panel_details.get('protocol')
            remark = inbound_panel_details.get('remark', f"AlamorVPN-{server_data['name']}")
            # آدرس تمیز شده (بدون http و پورت)
            address = server_data['subscription_base_url'].split('//')[1].split(':')[0].split('/')[0]
            port = inbound_panel_details.get('port')

            stream_settings = json.loads(inbound_panel_details.get('streamSettings', '{}'))
            network = stream_settings.get('network', 'tcp')
            security = stream_settings.get('security', 'none')

            config_url = ""
            if protocol == 'vless':
                flow = ""
                if security == 'xtls':
                    xtls_settings = stream_settings.get('xtlsSettings', {})
                    flow = xtls_settings.get('flow', 'xtls-rprx-direct')

                # Base URL
                config_url = f"vless://{client_uuid}@{address}:{port}"
                
                # Parameters
                params = {
                    'type': network,
                    'security': security,
                    'flow': flow,
                }

                if network == 'ws':
                    ws_settings = stream_settings.get('wsSettings', {})
                    params['path'] = ws_settings.get('path', '/')
                    params['host'] = ws_settings.get('headers', {}).get('Host', address)
                elif network == 'grpc':
                    grpc_settings = stream_settings.get('grpcSettings', {})
                    params['serviceName'] = grpc_settings.get('serviceName', '')
                
                if security in ['tls', 'xtls', 'reality']:
                    tls_settings = stream_settings.get('tlsSettings', {})
                    params['sni'] = tls_settings.get('serverName', address)
                    params['fp'] = tls_settings.get('fingerprint', '')
                    if security == 'reality':
                         params['pbk'] = tls_settings.get('publicKey', '')
                         params['sid'] = tls_settings.get('shortId', '')

                # Filter out empty params and join
                query_string = '&'.join([f"{k}={quote(str(v))}" for k, v in params.items() if v])
                config_url += f"?{query_string}#{quote(remark)}"

            # Add other protocols like VMess if needed
            
            if config_url:
                return {
                    "remark": remark,
                    "protocol": protocol,
                    "network": network,
                    "url": config_url
                }
        except Exception as e:
            logger.error(f"Error generating single config URL: {e}", exc_info=True)
            return None
        return None
    
