"""
Image file processing utilities.

All functions that touch the filesystem operate relative to the project root
so they work the same way in development and on Gandi.net.  Callers are
responsible for wrapping these in try/except and surfacing errors to the user.
"""

import mimetypes
import os
import uuid

from PIL import Image, ImageOps
from werkzeug.utils import secure_filename

# Extensions that can be safely processed by Pillow.
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# MIME types that correspond to the allowed extensions.
# Checked alongside extension so a renamed file (e.g. script.php → image.jpg)
# is rejected by content-type before it reaches Pillow.
ALLOWED_MIME_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}

# Files larger than this are rejected before any disk I/O occurs.
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# Uploaded images are resized to fit within this bounding box.
# Keeping a maximum dimension prevents very large originals from consuming
# excessive disk space on the Gandi.net Simple+ plan.
LARGE_SIZE = (1200, 1200)


def allowed_file(filename):
  """Return True if filename has an extension in ALLOWED_EXTENSIONS."""
  return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_size(file_object):
  """
  Return the size of file_object in bytes without consuming it.

  Seeks to the end to measure, then rewinds to the start so the caller
  can still read or save the file afterwards.
  """
  file_object.seek(0, 2)
  size = file_object.tell()
  file_object.seek(0)
  return size


def generate_filename(original_filename):
  """
  Return a UUID-based filename that preserves the original extension.

  Using a UUID prevents filename collisions and avoids leaking the
  uploader's original filename in public URLs.
  """
  _name, extension = os.path.splitext(secure_filename(original_filename))
  unique_id = str(uuid.uuid4())
  return f'{unique_id}{extension.lower()}'


def get_upload_path(filename):
  """Return the absolute-ish path to the uploads folder for the given filename."""
  upload_folder = os.path.join('app', 'static', 'uploads')
  return os.path.join(upload_folder, filename)


def resize_image(image_path, max_size):
  """
  Open, auto-orient, convert to RGB if needed, resize, and return a PIL Image.

  EXIF orientation is corrected so that photos taken on a rotated phone
  display right-side up without relying on CSS transforms.
  RGBA and palette-mode images are converted to RGB so JPEG output works.
  """
  with Image.open(image_path) as img:
    img = ImageOps.exif_transpose(img)

    if img.mode in ('RGBA', 'P'):
      # Flatten transparency onto a white background before converting.
      rgb_canvas = Image.new('RGB', img.size, (255, 255, 255))
      if img.mode == 'P':
        img = img.convert('RGBA')
      rgb_canvas.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
      img = rgb_canvas

    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    return img


def process_uploaded_image(file_object, original_filename):
  """
  Validate, resize, and save an uploaded image.  Return a dict of file metadata.

  The returned dict contains:
    filename        – original filename as supplied by the uploader
    stored_filename – UUID-based name used on disk
    file_path       – path relative to the static folder (e.g. uploads/<uuid>.jpg)
    file_size       – final file size on disk in bytes
    mime_type       – detected MIME type
    width           – pixel width after resizing
    height          – pixel height after resizing

  Raises ValueError with a user-facing message if validation fails or if
  Pillow cannot process the file.  Cleans up partial files on error.
  """
  if not file_object:
    raise ValueError('No file provided.')

  if not allowed_file(original_filename):
    raise ValueError('File type not allowed.  Please use PNG, JPG, JPEG, GIF, or WebP.')

  # Check the MIME type reported by the browser in addition to the extension.
  # This is not a substitute for Pillow's own format validation (which runs
  # later), but it catches obvious spoofing (e.g. a PHP file renamed .jpg)
  # before any bytes are written to disk.
  content_type = getattr(file_object, 'content_type', None) or getattr(file_object, 'mimetype', None)
  if content_type and content_type.split(';')[0].strip() not in ALLOWED_MIME_TYPES:
    raise ValueError(f'File type not allowed (content-type: {content_type}).')

  file_size = get_file_size(file_object)
  if file_size > MAX_FILE_SIZE:
    max_mb = MAX_FILE_SIZE // (1024 * 1024)
    raise ValueError(f'File too large.  Maximum size is {max_mb} MB.')

  stored_filename = generate_filename(original_filename)
  upload_path = get_upload_path(stored_filename)

  upload_dir = os.path.dirname(upload_path)
  os.makedirs(upload_dir, exist_ok=True)

  # Write a temp file first so that if Pillow fails we can clean up
  # the temp copy without leaving a broken file at the final path.
  temp_path = upload_path + '.tmp'
  file_object.save(temp_path)

  try:
    img = resize_image(temp_path, LARGE_SIZE)
    width, height = img.size

    is_jpeg = stored_filename.lower().endswith(('.jpg', '.jpeg'))
    if is_jpeg:
      img.save(upload_path, 'JPEG', quality=95, optimize=True)
    else:
      img.save(upload_path, optimize=True)

    if os.path.exists(temp_path):
      os.remove(temp_path)

    mime_type = mimetypes.guess_type(stored_filename)[0] or 'application/octet-stream'

    return {
      'filename': original_filename,
      'stored_filename': stored_filename,
      'file_path': f'uploads/{stored_filename}',
      'file_size': os.path.getsize(upload_path),
      'mime_type': mime_type,
      'width': width,
      'height': height,
    }

  except Exception as processing_error:
    for path in [temp_path, upload_path]:
      if os.path.exists(path):
        os.remove(path)
    raise ValueError(f'Error processing image: {processing_error}')


def delete_image_file(stored_filename):
  """
  Delete the stored image file from disk.  Return True if deleted, False if not found.

  Does nothing and returns False if stored_filename is empty or None,
  so callers do not need to guard against missing filenames.
  """
  if not stored_filename:
    return False
  file_path = get_upload_path(stored_filename)
  if os.path.exists(file_path):
    os.remove(file_path)
    return True
  return False


def generate_thumbnail_url(stored_filename):
  """
  Return the URL path for the stored image.

  Thumbnail generation is not implemented yet; this returns the full-size
  URL so the template layer does not need to change when thumbnails are added.
  """
  return f'/static/uploads/{stored_filename}'
