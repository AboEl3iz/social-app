from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordResetForm
from django.contrib.auth.decorators import login_required
from .models import Profile, Settings
from django.core.mail import send_mail
from django.conf import settings
from .forms import UserRegisterForm, ProfileForm, SettingsForm, UserLoginForm
from django.contrib.auth.models import User
from django.contrib import messages
from django.urls import reverse
from django.template.loader import render_to_string

# Create your views here.

# Registration view

def register_view(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            Profile.objects.create(user=user)
            Settings.objects.create(user=user)
            # Send welcome email
            welcome_message = f"""
            Welcome to SocialHub, {user.username}!
            
            Thank you for joining our community. Here's what you can do:
            - Create and share posts with images
            - Follow other users
            - Like and comment on posts
            - Search for users and content
            - Customize your profile and privacy settings
            
            Get started by creating your first post!
            
            Best regards,
            The SocialHub Team
            """
            send_mail(
                'Welcome to SocialHub!',
                welcome_message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=True,
            )
            messages.success(request, 'Registration successful! Please log in.')
            return redirect('users:login')
    else:
        form = UserRegisterForm()
    return render(request, 'users/register.html', {'form': form})

# Login view

def login_view(request):
    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('posts:home_feed')
    else:
        form = UserLoginForm()
    return render(request, 'users/login.html', {'form': form})

# Logout view

def logout_view(request):
    logout(request)
    return redirect('users:login')

# Profile view
@login_required
def profile_view(request, username):
    user = get_object_or_404(User, username=username)
    profile, created = Profile.objects.get_or_create(user=user)
    
    # Get user settings to check profile visibility
    try:
        user_settings = Settings.objects.get(user=user)
    except Settings.DoesNotExist:
        # Create settings if they don't exist
        user_settings = Settings.objects.create(user=user)
    
    is_owner = request.user == user
    
    # Check if profile is visible to the current user
    if not is_owner and not user_settings.profile_visible:
        messages.warning(request, f"{user.username}'s profile is private and not visible.")
        return render(request, 'users/profile_private.html', {
            'profile_user': user,
            'is_owner': False
        })
    
    # Filter posts based on privacy settings and relationship
    all_posts = user.post_set.all()
    posts = []
    
    if is_owner:
        # Profile owner can see all their own posts
        posts = all_posts
    else:
        # Filter posts based on privacy level
        from users.models import Follow
        for post in all_posts:
            if user_settings.privacy == 'public':
                posts.append(post)
            elif user_settings.privacy == 'friends':
                # Only show to followers
                if Follow.objects.filter(follower=request.user, following=user).exists():
                    posts.append(post)
            # Private posts are not shown to others (already handled)
    
    # Get blocked users if the profile owner is viewing their own profile
    blocked_users = []
    if is_owner:
        from posts.models import Block
        blocked_users = Block.objects.filter(blocker=user).select_related('blocked_user')
    
    # Get following/followers data
    from users.models import Follow
    following = Follow.objects.filter(follower=user).select_related('following')
    followers = Follow.objects.filter(following=user).select_related('follower')
    
    # Count stats
    following_count = following.count()
    followers_count = followers.count()
    posts_count = len(posts)
    
    if is_owner:
        if request.method == 'POST':
            form = ProfileForm(request.POST, request.FILES, instance=profile)
            if form.is_valid():
                form.save()
                messages.success(request, 'Profile updated!')
                return redirect('users:profile', username=user.username)
        else:
            form = ProfileForm(instance=profile)
    else:
        form = None
    return render(request, 'users/profile.html', {
        'profile': profile, 
        'posts': posts, 
        'is_owner': is_owner, 
        'form': form,
        'blocked_users': blocked_users,
        'following': following,
        'followers': followers,
        'following_count': following_count,
        'followers_count': followers_count,
        'posts_count': posts_count
    })

# Settings view
@login_required
def settings_view(request):
    settings_obj = Settings.objects.get(user=request.user)
    if request.method == 'POST':
        form = SettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Settings updated!')
            return redirect('users:settings')
    else:
        form = SettingsForm(instance=settings_obj)
    return render(request, 'users/settings.html', {'form': form})

# Password reset view

def password_reset_view(request):
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            form.save(
                request=request,
                use_https=request.is_secure(),
                email_template_name='users/password_reset_email.html',
                subject_template_name='users/password_reset_subject.txt',
            )
            messages.success(request, 'Password reset email sent!')
            return redirect('users:login')
    else:
        form = PasswordResetForm()
    return render(request, 'users/password_reset.html', {'form': form})

# Email notification functions
def send_like_notification(post, liker):
    """Send email notification when someone likes your post"""
    if post.user != liker and post.user.settings.email_notifications:
        subject = f'{liker.username} liked your post'
        message = f"""
        Hi {post.user.username},
        
        {liker.username} just liked your post: "{post.text[:50]}{'...' if len(post.text) > 50 else ''}"
        
        View your post: http://127.0.0.1:8000/posts/post/{post.id}/
        
        Best regards,
        SocialHub Team
        """
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [post.user.email],
            fail_silently=True,
        )

def send_comment_notification(post, commenter):
    """Send email notification when someone comments on your post"""
    if post.user != commenter and post.user.settings.email_notifications:
        subject = f'{commenter.username} commented on your post'
        message = f"""
        Hi {post.user.username},
        
        {commenter.username} just commented on your post: "{post.text[:50]}{'...' if len(post.text) > 50 else ''}"
        
        Comment: "{commenter.comment_set.last().text}"
        
        View your post: http://127.0.0.1:8000/posts/post/{post.id}/
        
        Best regards,
        SocialHub Team
        """
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [post.user.email],
            fail_silently=True,
        )

def send_follow_notification(follower, following):
    """Send email notification when someone follows you"""
    if following.settings.email_notifications:
        subject = f'{follower.username} started following you'
        message = f"""
        Hi {following.username},
        
        {follower.username} just started following you on SocialHub!
        
        View their profile: http://127.0.0.1:8000/users/profile/{follower.username}/
        
        Best regards,
        SocialHub Team
        """
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [following.email],
            fail_silently=True,
        )
