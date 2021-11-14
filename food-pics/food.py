from food_post import FoodPost
import os
from typing import List, Optional
from praw import Reddit
from praw.models import Submission
from redis import Redis, from_url as init_reddis_client
import requests
import random
import logging
import sys


def get_submission(redis_client: Redis, 
                   reddit_client: Reddit, 
                   subs: str, 
                   request_limit: int) -> Optional[Submission]:
    """
    Retrieve a "hot" post from the list of subreddits defined in the
    'SUBREDDITS' environment variable, returning the PRAW model of a
    post (submission).
    @param redis_client  Redis client to interface with Heroku Redis
    @param reddit_client PRAW Reddit client
    @return a "hot" post from the list of subreddits, or None if there are no 
            posts, or an error occurs
    """
    # fallback in case all of the posts are already used
    submissions: List[Submission] = []
    try:
        for submission in reddit_client.subreddit(subs).hot(limit=request_limit):
            submissions.append(submission)
            if not redis_client.exists(submission.id):
                redis_client.set(submission.id, '1')
                return submission  # short-circuit early if we know this is new
    except Exception:
        logging.exception('An unexpected error occurred')
        return None
    # if we did not return before this, then all of the hot posts
    # returned have already been posted. default to return a random one,
    # rather than try the search again to limit execution time
    if len(submissions) > 0:
        return random.choice(submissions)
    else:
        return None


def main():
    # Read the Redis URL from the environment. This value gets injected
    # by Heroku
    r = init_reddis_client(os.getenv('REDIS_URL'), decode_responses=True)

    webhook_url = os.getenv('WEBHOOK_URL')

    reddit_client_id = os.getenv('REDDIT_CLIENT_ID')
    reddit_client_secret = os.getenv('REDDIT_CLIENT_SECRET')
    # expected to be a list of subreddits to search, separated by +
    # example: "foo+bar+baz" where foo, bar, and baz are all subreddits
    subs = os.getenv('SUBREDDITS')
    request_limit = int(os.getenv(key='LIMIT', default='24'))

    if webhook_url is None:
        logging.error('No webhook URL specified in environment')
        sys.exit(1)
    if reddit_client_id is None or reddit_client_secret is None:
        logging.error('Reddit API credentials not configured in environment')
        sys.exit(1)
    if subs is None:
        logging.error('No subreddits list defined in environment')
        sys.exit(1)

    reddit = Reddit(
        client_id=reddit_client_id,
        client_secret=reddit_client_secret,
        user_agent='discord:food_waifu:v0.2'
    )

    submission = get_submission(r, reddit, subs, request_limit)
    embed = FoodPost.from_submission(submission).to_embed()
    data = {
        "content": submission.title,
        "username": "Saxy's Food Webhook",
        "embeds": [embed]
    }
    logging.info(data)
    result = requests.post(url=webhook_url, data=data)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(err)
    else:
        print("Payload delivered successfully, code {}.".format(result.status_code))


if __name__ == '__main__':
    main()
