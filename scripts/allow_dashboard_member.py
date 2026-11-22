"""Allow a group member's email to register for the dashboard. Does not send email."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import sys

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-id', required=True)
    parser.add_argument('--email', required=True)
    parser.add_argument('--viewer', action='store_true', help='Group access without Spotify collection')
    parser.add_argument('--name')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--table', default='sfw-dev', help='Main table (plays, profiles, membership)')
    parser.add_argument('--connect-table', default='sfw-dev-connect', help='Invitations and approved emails')
    parser.add_argument('--group', default='friends')
    args = parser.parse_args()
    os.environ.setdefault('AWS_DEFAULT_REGION', args.region)
    os.environ['TABLE_NAME'] = args.table
    import store
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,39}', args.user_id):
        parser.error('--user-id must use 2-40 lowercase letters, digits or hyphens')
    if not args.viewer and args.user_id not in store.group_members(args.group):
        parser.error(f'{args.user_id} is not a Spotify member of {args.group}: '
                     'connect Spotify first, or register observers with --viewer')
    email = args.email.strip().casefold()
    key = 'EMAIL#' + hashlib.sha256(email.encode()).hexdigest()
    boto3.resource('dynamodb', region_name=args.region).Table(args.connect_table).put_item(
        Item={'id': key, 'user_id': args.user_id, 'group_id': args.group},
        ConditionExpression='attribute_not_exists(id) OR user_id = :u',
        ExpressionAttributeValues={':u': args.user_id})
    if args.viewer:
        boto3.resource('dynamodb', region_name=args.region).Table(args.table).put_item(
            Item={'PK': 'GROUP#' + args.group, 'SK': 'VIEWER#' + args.user_id,
                  'user_id': args.user_id, 'display_name': args.name or args.user_id.title()})
    print(args.user_id + ': dashboard registration enabled')


if __name__ == '__main__':
    main()
