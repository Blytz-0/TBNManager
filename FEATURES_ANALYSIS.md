# TBNManager Feature Analysis & Premium Plan

## Overview
This document analyzes all features in TBNManager and defines which should be free vs premium.

## Current Feature Structure

### Free Features (DEFAULT_FEATURES)
Core community management features available to all servers:

| Feature ID | Display Name | Status | Description |
|------------|--------------|--------|-------------|
| `strikes` | Strike System | ✅ Implemented | Issue strikes to players, track violations |
| `tickets` | Support Tickets | ✅ Implemented | Support ticket system with transcripts |
| `player_linking` | Player Linking (Steam/Alderon) | ✅ Implemented | Link Discord accounts to Steam/Alderon IDs |
| `role_selection` | Self-Service Role Selection | ✅ Implemented | Allow members to self-assign roles |
| `announcements` | Server Announcements | ✅ Implemented | Send announcements to configured channels |
| `audit_log` | Audit Logging | ✅ Implemented | Track all admin actions (strikes, bans, config changes) |
| `auto_ban` | Auto-Ban (3 strikes) | ✅ Implemented | Automatically ban users after 3 strikes |
| `dm_notifications` | DM Notifications | ✅ Implemented | Notify users via DM about strikes/bans |

### Premium Features (PREMIUM_FEATURES)
Advanced features requiring subscription:

| Feature ID | Display Name | Status | Description |
|------------|--------------|--------|-------------|
| `rcon` | RCON Integration | ✅ Implemented | Direct server commands (kick, ban, announce, verify) |
| `pterodactyl` | Pterodactyl Panel Control | ❌ Not Implemented | Server power control, file management, console access |
| `log_monitoring` | SFTP Log Monitoring | ✅ Implemented | Real-time game logs (chat, kills, admin actions, join/leave) |
| `advanced_analytics` | Advanced Analytics | ❌ Not Implemented | Player statistics, trends, retention metrics |
| `custom_branding` | Custom Bot Branding | ❌ Not Implemented | Custom bot avatar, name, embed colors |
| `api_access` | REST API Access | ❌ Not Implemented | External API access to bot data |

## Feature Categorization Rationale

### Why These Features Are FREE:
1. **Strike System** - Core moderation tool, essential for community management
2. **Support Tickets** - Basic support infrastructure every community needs
3. **Player Linking** - Foundation for other features, enables verification
4. **Role Selection** - Quality of life feature, reduces admin workload
5. **Announcements** - Essential communication tool
6. **Audit Logging** - Transparency and accountability, should be available to all
7. **Auto-Ban** - Automated enforcement, saves admin time (based on free strike system)
8. **DM Notifications** - User experience improvement, keeps members informed

### Why These Features Are PREMIUM:
1. **RCON Integration** - Direct game server control, advanced automation capability
   - Requires additional infrastructure (RCON server connection)
   - High value for game server operators
   - Supports multi-server setups (2-5 servers per guild)

2. **Pterodactyl Panel Control** - Full server management from Discord
   - Power control (start/stop/restart)
   - File browsing and editing
   - Console command execution
   - Significant value for server hosts

3. **SFTP Log Monitoring** - Real-time game event feeds
   - Continuous SFTP connections (resource intensive)
   - Advanced parsing and display
   - Multiple log types (chat, kills, admin, join/leave)
   - Configurable channel routing
   - Admin detection via Game.ini parsing

4. **Advanced Analytics** - Business intelligence features
   - Complex data processing
   - Historical trend analysis
   - Player retention metrics

5. **Custom Branding** - White-label capabilities
   - Premium customization option
   - Appeals to larger communities

6. **REST API Access** - Integration capabilities
   - Enables custom integrations
   - Requires API infrastructure
   - Advanced use case

## Implementation Status

### ✅ Fully Implemented Features
- Strike System (with enhanced passport display)
- Support Tickets (with custom emojis and color)
- Player Linking (Steam + Alderon IDs with passport card)
- Role Selection
- Announcements
- Audit Logging
- Auto-Ban (3 strikes)
- DM Notifications
- **RCON Integration** (multi-server, verification, auto-enforcement)
- **SFTP Log Monitoring** (chat, kills, admin, join/leave with Game.ini admin detection)

### ❌ Not Yet Implemented
- **Pterodactyl Panel Control** (planned premium feature - power, files, console)
- Advanced Analytics (future premium feature)
- Custom Branding (future premium feature)
- REST API Access (future premium feature)

## Premium Tier Structure (Proposed)

### Tier 1: Free
- All DEFAULT_FEATURES
- Unlimited Discord server usage
- Community support

### Tier 2: RCON Premium ($X/month)
- All Free features
- RCON Integration
- Unlimited game servers per Discord guild
- In-game verification
- Auto-kick/ban enforcement
- Priority support

### Tier 3: Pterodactyl Premium ($Y/month)
- All Free features
- Pterodactyl Panel Control
- Server power management
- File browsing & editing
- Console access
- Priority support

### Tier 4: Full Premium ($Z/month - discounted bundle)
- All Free features
- RCON Integration
- Pterodactyl Control
- SFTP Log Monitoring
- Multi-server support (unlimited)
- Priority support
- Early access to new features

### Tier 5: Enterprise (Custom pricing)
- All Full Premium features
- Advanced Analytics
- Custom Branding
- REST API Access
- Dedicated support
- Custom feature development

## Database Schema Support

All features are stored in the `guild_features` table:
```sql
CREATE TABLE guild_features (
    guild_id BIGINT,
    feature VARCHAR(50),
    enabled BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (guild_id, feature)
);
```

Premium status tracked in `guilds` table:
```sql
ALTER TABLE guilds ADD COLUMN is_premium BOOLEAN DEFAULT FALSE;
ALTER TABLE guilds ADD COLUMN premium_until TIMESTAMP NULL;
```

## Feature Toggle System

Features can be toggled via `/feature` command:
- Admins can enable/disable any free feature
- Premium features require `is_premium = TRUE`
- System checks premium status before allowing premium feature usage

## Permission System Integration

Each feature has associated commands defined in `FEATURE_COMMANDS` (config/commands.py):
- `strikes`: strike, viewstrikes, clearstrikes, etc.
- `tickets`: ticket (user command), ticketsetup, closeticket
- `player_linking`: myid, playerid, linksteam, linkalderon
- `rcon`: rcon commands (addserver, kick, ban, announce, verify)
- `pterodactyl`: server commands (start, stop, restart, files)
- `log_monitoring`: logs commands (setup, setchannel, start, stop)

## Recommendations

### Short Term (Current)
1. ✅ Keep current free/premium split
2. ✅ Update display names to be more descriptive (completed)
3. ✅ Show "SFTP Log Monitoring" instead of "log_monitoring" (completed)
4. Implement Stripe subscription system
5. Add premium tier selection in bot

### Medium Term (3-6 months)
1. Implement Advanced Analytics
   - Player activity heatmaps
   - Strike/ban trends
   - Server population metrics
   - Top players by playtime
2. Add Custom Branding
   - Custom embed colors
   - Custom footer text
   - Upload custom bot avatar (per-guild appearance)
3. Build REST API
   - Authentication via API keys
   - Endpoints for strikes, players, server status
   - Webhook notifications

### Long Term (6-12 months)
1. Multi-region game server support
2. Discord Slash command builder (custom commands per guild)
3. Advanced automation rules (if-then logic)
4. Player retention campaigns (automated DMs for inactive players)
5. Integration marketplace (connect to other game tools)

## Feature Usage Metrics (To Track)

Once implemented, track these metrics to validate premium value:
- RCON commands executed per guild per month
- Pterodactyl actions per guild per month
- Log entries processed per guild per month
- Number of game servers per guild
- API calls per guild per month

This data will inform future pricing and feature development decisions.

## Migration Path

For existing users when premium system launches:
1. All existing guilds get 30-day free trial of Full Premium
2. After trial: free features remain enabled
3. Premium features require subscription to continue
4. Grace period: 7 days to subscribe before premium features disabled
5. Existing RCON/Pterodactyl configs preserved (just disabled until subscribed)

---

**Last Updated:** 2026-01-31
**Version:** 1.0
