from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Post, Comment, Like
from .forms import PostForm, CommentForm
from django.db.models import Q
from .models import Category, Tag, Report, Block
from users.models import Follow
from users.views import send_like_notification, send_comment_notification, send_follow_notification
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import get_user_model

User = get_user_model()

# Create your views here.

# Home feed view with search and filtering

def home_feed(request):
    query = request.GET.get('q', '')
    category_id = request.GET.get('category', '')
    tag_name = request.GET.get('tag', '')
    
    posts = Post.objects.all()
    
    if query:
        posts = posts.filter(
            Q(text__icontains=query) | 
            Q(user__username__icontains=query) |
            Q(tags__name__icontains=query)
        ).distinct()
    
    if category_id:
        posts = posts.filter(category_id=category_id)
    
    if tag_name:
        posts = posts.filter(tags__name=tag_name)
    
    # Filter posts based on privacy settings
    from users.models import Settings, Follow
    filtered_posts = []
    
    for post in posts:
        try:
            post_owner_settings = Settings.objects.get(user=post.user)
            privacy_level = post_owner_settings.privacy
            
            # Always show own posts
            if post.user == request.user:
                filtered_posts.append(post)
            # Public posts - show to everyone
            elif privacy_level == 'public':
                filtered_posts.append(post)
            # Friends posts - show only to followers
            elif privacy_level == 'friends':
                if Follow.objects.filter(follower=request.user, following=post.user).exists():
                    filtered_posts.append(post)
            # Private posts - don't show to anyone except owner
            # (already handled by the first condition)
                
        except Settings.DoesNotExist:
            # If no settings exist, create default settings (public) and show post
            Settings.objects.create(user=post.user)
            filtered_posts.append(post)
    
    posts = filtered_posts
    posts.sort(key=lambda x: x.timestamp, reverse=True)
    categories = Category.objects.all()
    
    return render(request, 'posts/feed.html', {
        'posts': posts, 
        'categories': categories,
        'query': query,
        'selected_category': category_id,
        'selected_tag': tag_name
    })

# Post detail view

def post_detail(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    comments = post.comments.all().order_by('timestamp')
    comment_form = CommentForm()
    return render(request, 'posts/post_detail.html', {'post': post, 'comments': comments, 'comment_form': comment_form})

# Create post view
@login_required
def create_post(request):
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.save()
            
            # Handle tags
            tag_names = form.cleaned_data.get('tags', [])
            if tag_names:
                for tag_name in tag_names:
                    tag, created = Tag.objects.get_or_create(name=tag_name.lower())
                    post.tags.add(tag)
            
            # Save many-to-many relationships (excluding tags since we handle them manually)
            form.save_m2m()
            return redirect('posts:home_feed')
    else:
        form = PostForm()
    return render(request, 'posts/create_post.html', {'form': form})

# Share post view
@login_required
def share_post(request, post_id):
    original_post = get_object_or_404(Post, id=post_id)
    
    if request.method == 'POST':
        shared_post = Post.objects.create(
            user=request.user,
            text=request.POST.get('text', ''),
            shared_from=original_post,
            is_shared=True
        )
        return redirect('posts:home_feed')
    
    return render(request, 'posts/share_post.html', {'original_post': original_post})

# Search users view
def search_users(request):
    query = request.GET.get('q', '')
    users = []
    
    if query:
        # Only show users who have profile_visible=True in their settings
        from users.models import Settings
        users = User.objects.filter(
            username__icontains=query
        ).exclude(id=request.user.id)
        
        # Filter out users with profile_visible=False
        visible_users = []
        for user in users:
            try:
                user_settings = Settings.objects.get(user=user)
                if user_settings.profile_visible:
                    visible_users.append(user)
            except Settings.DoesNotExist:
                # If no settings exist, create default settings and include user
                Settings.objects.create(user=user)
                visible_users.append(user)
        
        users = visible_users
    
    return render(request, 'users/search_users.html', {'users': users, 'query': query})

# Follow user view
@login_required
def follow_user(request, user_id):
    user_to_follow = get_object_or_404(User, id=user_id)
    
    if request.user != user_to_follow:
        follow, created = Follow.objects.get_or_create(
            follower=request.user,
            following=user_to_follow
        )
        if created:
            # Send follow notification email
            send_follow_notification(request.user, user_to_follow)
        else:
            follow.delete()
    
    return redirect('posts:search_users')

# Report user/post view
@login_required
def report_user(request, user_id):
    reported_user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        Report.objects.create(
            reporter=request.user,
            reported_user=reported_user,
            reason=request.POST.get('reason'),
            description=request.POST.get('description', '')
        )
        messages.success(request, 'Report submitted successfully.')
        return redirect('posts:search_users')
    
    return render(request, 'users/report_user.html', {'reported_user': reported_user})

# Block user view
@login_required
def block_user(request, user_id):
    user_to_block = get_object_or_404(User, id=user_id)
    
    if request.user != user_to_block:
        block, created = Block.objects.get_or_create(
            blocker=request.user,
            blocked_user=user_to_block
        )
        if not created:
            block.delete()
    
    return redirect('posts:search_users')

# Unblock user view
@login_required
def unblock_user(request, user_id):
    user_to_unblock = get_object_or_404(User, id=user_id)
    
    try:
        block = Block.objects.get(
            blocker=request.user,
            blocked_user=user_to_unblock
        )
        block.delete()
        messages.success(request, f'You have unblocked {user_to_unblock.username}.')
    except Block.DoesNotExist:
        messages.warning(request, f'{user_to_unblock.username} was not blocked.')
    
    return redirect('users:profile', username=request.user.username)

# Like/unlike post (AJAX)
@login_required
def like_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    liked = False
    like_obj = Like.objects.filter(post=post, user=request.user)
    if like_obj.exists():
        like_obj.delete()
    else:
        Like.objects.create(post=post, user=request.user)
        liked = True
        # Send like notification email
        send_like_notification(post, request.user)
    return JsonResponse({'liked': liked, 'like_count': post.likes.count()})

# Add comment
@login_required
def add_comment(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.user = request.user
            comment.post = post
            comment.save()
            # Send comment notification email
            send_comment_notification(post, request.user)
    return redirect('posts:post_detail', post_id=post_id)

# Edit comment
@login_required
def edit_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id, user=request.user)
    if request.method == 'POST':
        form = CommentForm(request.POST, instance=comment)
        if form.is_valid():
            form.save()
            return redirect('posts:post_detail', post_id=comment.post.id)
    else:
        form = CommentForm(instance=comment)
    return render(request, 'posts/edit_comment.html', {'form': form})

# Delete comment
@login_required
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id, user=request.user)
    post_id = comment.post.id
    comment.delete()
    return redirect('posts:post_detail', post_id=post_id)
